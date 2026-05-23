import hashlib
import struct
import zlib
from django.core.files.base import ContentFile
from core.models import (
    Challenge, ChallengeTemplate, TemplateVariable,
    CTFSession, Category,
)


class ChallengeBuilderService:
    """
    Service responsible for assembling a Challenge from an Elementary Brick
    (ChallengeTemplate) and instructor-supplied parameters.
    Respects the Open/Closed Principle: new template types require zero changes here.
    """

    @classmethod
    def build_challenge(
        cls,
        session_id: int,
        category_id: int,
        template_id: int,
        title: str,
        base_points: int,
        custom_params_dict: dict,
        custom_description: str | None = None,
        internal_port: int | None = None,
    ) -> Challenge:
        """
        Validates required variables, merges defaults with instructor overrides,
        and persists a fully-configured Challenge ready for deployment.
        Automatically detects STATIC vs CONTAINER based on the template's docker image.

        Args:
            custom_description: If supplied, overrides the template's base description text.
                                 Supports Markdown. Falls back to template.description if None.
            internal_port:       The container-internal port Traefik should route to.
                                 Overrides the Challenge model default (80) for CONTAINER types.
                                 Ignored for STATIC challenges.
        """

        template = ChallengeTemplate.objects.get(pk=template_id)
        session = CTFSession.objects.get(pk=session_id)
        category = Category.objects.get(pk=category_id)

        # --- Validate required TemplateVariables are present ---
        required_vars = TemplateVariable.objects.filter(
            template=template, is_required=True
        )
        missing = [
            v.key_name for v in required_vars
            if v.key_name not in custom_params_dict
        ]
        if missing:
            raise ValueError(
                f"Missing required template variables: {', '.join(missing)}"
            )

        # --- Build the final parameter dict (defaults + overrides) ---
        final_params = {}
        for tvar in template.variables.all():
            if tvar.default_value:
                final_params[tvar.key_name] = tvar.default_value
        final_params.update(custom_params_dict)

        # --- Auto-generate the flag_hash from the FLAG parameter ---
        raw_flag = final_params.get("FLAG", f"FLAG{{{title.replace(' ', '_')}}}")
        flag_hash = hashlib.sha256(raw_flag.encode("utf-8")).hexdigest()

        # --- Determine challenge_type from template ---
        has_docker = bool(template.base_docker_image and template.base_docker_image.strip())
        challenge_type = "CONTAINER" if has_docker else "STATIC"

        # --- Build the description (may be enriched by cipher generators) ---
        # Honour instructor's custom text if provided; otherwise fall back to template base.
        description = custom_description if custom_description else template.description
        description = cls._apply_cipher_enrichment(template, final_params, description)

        # --- Security: strip sensitive keys before DB persistence ---
        # The raw flag is now secured inside flag_hash (SHA-256). Storing
        # it again as plaintext in the JSONField would expose it to anyone
        # with read access to the database or Django admin.
        # Rule: any parameter whose key is "FLAG" is considered a secret
        # and MUST NOT be persisted in custom_parameters.
        _SENSITIVE_PARAM_KEYS = {"FLAG"}
        safe_params = {
            k: v for k, v in final_params.items() if k not in _SENSITIVE_PARAM_KEYS
        }

        # --- Resolve the final internal port for CONTAINER challenges ---
        # Priority: instructor override -> model default (80).
        create_kwargs = dict(
            session=session,
            category=category,
            template=template,
            title=title,
            description=description,
            base_points=base_points,
            flag_hash=flag_hash,
            challenge_type=challenge_type,
            docker_image_tag=template.base_docker_image if has_docker else None,
            custom_parameters=safe_params,  # FLAG is secured in flag_hash, NOT here
        )
        if has_docker and internal_port is not None:
            create_kwargs["internal_port"] = internal_port

        challenge = Challenge.objects.create(**create_kwargs)

        # --- Post-creation: generate and attach files if needed ---
        # NOTE: We pass final_params (which still contains the raw FLAG) to the
        # attachment generator because embedding the flag in a stego image is an
        # intentional, transient in-memory operation. The raw flag never hits the DB
        # through this path.
        cls._apply_attachment_generation(template, final_params, challenge)

        return challenge

    # --- Cipher Enrichment Strategies (SOLID: isolated, extensible) ---

    @classmethod
    def _apply_cipher_enrichment(cls, template, params: dict, description: str) -> str:
        """
        Dispatcher that enriches the challenge description based on vulnerability_type.
        New ciphers can be added here without touching the main build flow.
        """
        if template.vulnerability_type == "crypto_caesar":
            plaintext = params.get("PLAINTEXT_MESSAGE", "")
            shift = int(params.get("SHIFT_AMOUNT", 3))
            ciphertext = cls._caesar_shift(plaintext, shift)
            description += f"\n\n**Ciphertext:** `{ciphertext}`"

        return description

    # --- Attachment Generation Strategies (SOLID: isolated, extensible) ---

    @classmethod
    def _apply_attachment_generation(cls, template, params: dict, challenge: Challenge):
        """
        Dispatcher that generates and attaches files based on vulnerability_type.
        New forensics types only need a new elif branch here.
        """
        if template.vulnerability_type == "forensics_eof_stego":
            flag_text = params.get("FLAG", "FLAG{default}")
            image_bytes = cls._generate_eof_stego_image(flag_text)
            filename = f"evidence_{challenge.id}.png"
            challenge.attachment.save(filename, ContentFile(image_bytes), save=True)

    # --- Private Helpers ---

    @staticmethod
    def _caesar_shift(text: str, shift: int) -> str:
        """
        Classic Caesar cipher: shifts only alphabetical characters by shift positions.
        Preserves case, digits, punctuation, and special characters.
        """
        result = []
        for char in text:
            if char.isalpha():
                base = ord('A') if char.isupper() else ord('a')
                shifted = (ord(char) - base + shift) % 26 + base
                result.append(chr(shifted))
            else:
                result.append(char)
        return ''.join(result)

    @staticmethod
    def _generate_eof_stego_image(flag_text: str) -> bytes:
        """
        Generates a minimal valid 1x1 red pixel PNG and appends the flag as
        raw bytes after the IEND chunk (classic EOF steganography technique).
        """
        # PNG Signature (8 bytes, mandatory)
        signature = b'\x89PNG\r\n\x1a\n'

        # IHDR chunk: 1x1 pixel, 8-bit RGB
        width = 1
        height = 1
        bit_depth = 8
        color_type = 2  # RGB
        ihdr_data = struct.pack('>IIBBBBB', width, height, bit_depth, color_type, 0, 0, 0)
        ihdr_chunk = cls_build_png_chunk(b'IHDR', ihdr_data)

        # IDAT chunk: single red pixel (filter byte 0 + R=255, G=0, B=0)
        raw_scanline = b'\x00\xff\x00\x00'  # filter=None + RGB(255,0,0)
        compressed = zlib.compress(raw_scanline)
        idat_chunk = cls_build_png_chunk(b'IDAT', compressed)

        # IEND chunk: marks end of valid PNG
        iend_chunk = cls_build_png_chunk(b'IEND', b'')

        # Assemble valid PNG
        png_bytes = signature + ihdr_chunk + idat_chunk + iend_chunk

        # Append the hidden flag AFTER the IEND (the steganography payload)
        stego_payload = flag_text.encode('utf-8')

        return png_bytes + stego_payload


def cls_build_png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Builds a single PNG chunk: [length][type][data][crc32]."""
    chunk_len = struct.pack('>I', len(data))
    chunk_crc = struct.pack('>I', zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    return chunk_len + chunk_type + data + chunk_crc
