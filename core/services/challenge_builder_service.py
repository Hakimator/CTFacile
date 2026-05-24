import base64
import hashlib
import struct
import zlib
from django.core.files.base import ContentFile
from core.models import (
    Challenge, ChallengeTemplate, TemplateVariable,
    CTFSession, Category, ChallengePrerequisite,
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
        is_entry_node: bool = False,
        prerequisite_ids: list | None = None,
    ) -> Challenge:
        """
        Validates required variables, merges defaults with instructor overrides,
        and persists a fully-configured Challenge ready for deployment.
        Automatically detects STATIC vs CONTAINER based on the template's docker image.

        Args:
            custom_description: If supplied, overrides the template base description text.
                                 Supports Markdown. Falls back to template.description if None.
            internal_port:       The container-internal port Traefik should route to.
                                 Overrides the Challenge model default (80) for CONTAINER types.
                                 Ignored for STATIC challenges.
        """
        template = ChallengeTemplate.objects.get(pk=template_id)
        session = CTFSession.objects.get(pk=session_id)
        category = Category.objects.get(pk=category_id)

        # --- Validate required TemplateVariables ---
        required_vars = TemplateVariable.objects.filter(template=template, is_required=True)
        missing = [v.key_name for v in required_vars if v.key_name not in custom_params_dict]
        if missing:
            raise ValueError(f"Missing required template variables: {', '.join(missing)}")

        # --- Build final parameter dict (defaults merged with instructor overrides) ---
        final_params = {}
        for tvar in template.variables.all():
            if tvar.default_value:
                final_params[tvar.key_name] = tvar.default_value
        final_params.update(custom_params_dict)

        # --- Hash the flag for secure storage ---
        raw_flag = final_params.get("FLAG", f"FLAG{{{title.replace(' ', '_')}}}")
        flag_hash = hashlib.sha256(raw_flag.encode("utf-8")).hexdigest()

        # --- Auto-detect challenge type ---
        has_docker = bool(template.base_docker_image and template.base_docker_image.strip())
        challenge_type = "CONTAINER" if has_docker else "STATIC"

        # --- Build description with cipher enrichment ---
        description = custom_description if custom_description else template.description
        description = cls._apply_cipher_enrichment(template, final_params, description)

        # --- Strip sensitive keys before DB write ---
        # FLAG is already secured as flag_hash. Never store plaintext flag in custom_parameters.
        _SENSITIVE_PARAM_KEYS = {"FLAG"}
        safe_params = {k: v for k, v in final_params.items() if k not in _SENSITIVE_PARAM_KEYS}

        # --- Create the challenge ---
        # Prerequisites take precedence: if any are supplied, is_entry_node is irrelevant.
        effective_entry_node = is_entry_node and not prerequisite_ids

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
            custom_parameters=safe_params,
            is_entry_node=effective_entry_node,
        )
        if has_docker and internal_port is not None:
            create_kwargs["internal_port"] = internal_port

        challenge = Challenge.objects.create(**create_kwargs)

        # --- Wire up prerequisites ---
        for prereq_id in (prerequisite_ids or []):
            try:
                required = Challenge.objects.get(pk=prereq_id)
                ChallengePrerequisite.objects.get_or_create(
                    target_challenge=challenge,
                    required_challenge=required,
                )
            except Challenge.DoesNotExist:
                pass

        # Attachment generation uses full final_params (including FLAG) — transient, never DB-stored
        cls._apply_attachment_generation(template, final_params, challenge)

        return challenge

    # =========================================================================
    # Cipher Enrichment Dispatcher
    # Add a new elif branch here to support a new vulnerability type.
    # Never touch build_challenge() for new types — Open/Closed Principle.
    # =========================================================================

    @classmethod
    def _apply_cipher_enrichment(cls, template, params: dict, description: str) -> str:

        vtype = template.vulnerability_type

        # --- Base64 Encoding ---
        if vtype == "crypto_base64":
            plaintext = params.get("PLAINTEXT_MESSAGE", "")
            encoded = base64.b64encode(plaintext.encode()).decode()
            description += (
                f"\n\n---\n"
                f"**Encoded message:**\n\n"
                f"```\n{encoded}\n```\n\n"
                f"*Hint: This is encoding, not encryption. No key required.*"
            )

        # --- Caesar Cipher ---
        elif vtype == "crypto_caesar":
            plaintext = params.get("PLAINTEXT_MESSAGE", "")
            shift = int(params.get("SHIFT_AMOUNT", 3))
            ciphertext = cls._caesar_shift(plaintext, shift)
            description += (
                f"\n\n---\n"
                f"**Shift:** `{shift}`\n\n"
                f"**Ciphertext:**\n\n"
                f"```\n{ciphertext}\n```"
            )

        # --- Vigenere Cipher ---
        elif vtype == "crypto_vigenere":
            plaintext = params.get("PLAINTEXT_MESSAGE", "").upper()
            key = params.get("KEY", "KEY").upper()
            ciphertext = cls._vigenere_encrypt(plaintext, key)
            description += (
                f"\n\n---\n"
                f"**Key:** `{key}`\n\n"
                f"**Ciphertext:**\n\n"
                f"```\n{ciphertext}\n```\n\n"
                f"*Non-alphabetic characters (spaces, punctuation) are passed through unchanged.*"
            )

        # --- Single-Byte XOR ---
        elif vtype == "crypto_xor":
            plaintext = params.get("PLAINTEXT_MESSAGE", "")
            key_hex = params.get("XOR_KEY_HEX", "41")
            key_byte = int(key_hex, 16)
            ciphertext_hex = cls._xor_encrypt(plaintext, key_byte)
            description += (
                f"\n\n---\n"
                f"**Ciphertext (hex bytes, space-separated):**\n\n"
                f"```\n{ciphertext_hex}\n```\n\n"
                f"*Hint: The encryption key is a single byte. "
                f"XOR is symmetric — the same operation decrypts. "
                f"Try all 256 possible key values and look for readable output.*"
            )

        # --- RSA with Small N ---
        elif vtype == "crypto_rsa_small":
            p = int(params.get("P", "61"))
            q = int(params.get("Q", "53"))
            e = int(params.get("E", "17"))
            secret = int(params.get("SECRET_NUMBER", "1337"))
            n = p * q
            c = pow(secret, e, n)
            description += (
                f"\n\n---\n"
                f"**RSA Public Key:**\n\n"
                f"```\nN = {n}\ne = {e}\n```\n\n"
                f"**Ciphertext:** `C = {c}`\n\n"
                f"*The plaintext M was encrypted as: C = M^e mod N*\n\n"
                f"*Hint: N is small enough to factor by hand or with a short script. "
                f"Once you have p and q, compute φ(N) = (p-1)(q-1), "
                f"then find d such that e·d ≡ 1 mod φ(N). "
                f"Decrypt with: M = C^d mod N. "
                f"The flag is FLAG followed by the decrypted number in braces.*"
            )

        return description

    # =========================================================================
    # Attachment Generation Dispatcher
    # =========================================================================

    @classmethod
    def _apply_attachment_generation(cls, template, params: dict, challenge: Challenge):
        if template.vulnerability_type == "forensics_eof_stego":
            flag_text = params.get("FLAG", "FLAG{default}")
            image_bytes = cls._generate_eof_stego_image(flag_text)
            filename = f"evidence_{challenge.id}.png"
            challenge.attachment.save(filename, ContentFile(image_bytes), save=True)

    # =========================================================================
    # Cipher Helper Methods
    # =========================================================================

    @staticmethod
    def _caesar_shift(text: str, shift: int) -> str:
        """Classic Caesar cipher. Shifts only alpha chars; preserves everything else."""
        result = []
        for char in text:
            if char.isalpha():
                base = ord('A') if char.isupper() else ord('a')
                result.append(chr((ord(char) - base + shift) % 26 + base))
            else:
                result.append(char)
        return ''.join(result)

    @staticmethod
    def _vigenere_encrypt(text: str, key: str) -> str:
        """
        Vigenere cipher (uppercase only). Non-alpha characters pass through unchanged.
        The key cycles only when an alpha character is encrypted.
        """
        result = []
        key_idx = 0
        for char in text:
            if char.isalpha():
                shift = ord(key[key_idx % len(key)]) - ord('A')
                encrypted = chr((ord(char.upper()) - ord('A') + shift) % 26 + ord('A'))
                result.append(encrypted)
                key_idx += 1
            else:
                result.append(char)
        return ''.join(result)

    @staticmethod
    def _xor_encrypt(text: str, key_byte: int) -> str:
        """Single-byte XOR. Returns hex bytes separated by spaces."""
        return ' '.join(f'{ord(c) ^ key_byte:02x}' for c in text)

    @staticmethod
    def _generate_eof_stego_image(flag_text: str) -> bytes:
        """
        Generates a minimal valid 1x1 red pixel PNG and appends the flag as
        raw bytes after the IEND chunk (classic EOF steganography technique).
        """
        signature = b'\x89PNG\r\n\x1a\n'
        width, height, bit_depth, color_type = 1, 1, 8, 2
        ihdr_data = struct.pack('>IIBBBBB', width, height, bit_depth, color_type, 0, 0, 0)
        ihdr_chunk = _build_png_chunk(b'IHDR', ihdr_data)
        raw_scanline = b'\x00\xff\x00\x00'
        idat_chunk = _build_png_chunk(b'IDAT', zlib.compress(raw_scanline))
        iend_chunk = _build_png_chunk(b'IEND', b'')
        png_bytes = signature + ihdr_chunk + idat_chunk + iend_chunk
        return png_bytes + flag_text.encode('utf-8')


def _build_png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    """Builds a single PNG chunk: [length][type][data][crc32]."""
    return (
        struct.pack('>I', len(data))
        + chunk_type
        + data
        + struct.pack('>I', zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


# Keep old name as alias so existing callers don't break
cls_build_png_chunk = _build_png_chunk
