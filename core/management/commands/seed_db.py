import hashlib
from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from core.models import (
    User, CTFSession, Team, TeamMembership,
    Category, Challenge, ChallengePrerequisite,
    ChallengeTemplate, TemplateVariable,
    Achievement, SiteSettings,
)
from core.constants import UserRole, ScoringMode, TriggerType
from core.services.challenge_builder_service import ChallengeBuilderService


def sha256(flag: str) -> str:
    return hashlib.sha256(flag.encode("utf-8")).hexdigest()


class Command(BaseCommand):
    help = "Flushes the database and seeds a complete, playable crypto CTF."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Wiping existing data..."))

        from core.models import TeamAchievement, WriteUp, SOSTicket, Submission, ActiveInstance
        TeamAchievement.objects.all().delete()
        Achievement.objects.all().delete()
        WriteUp.objects.all().delete()
        SOSTicket.objects.all().delete()
        Submission.objects.all().delete()
        ActiveInstance.objects.all().delete()
        TemplateVariable.objects.all().delete()
        ChallengeTemplate.objects.all().delete()
        ChallengePrerequisite.objects.all().delete()
        Challenge.objects.all().delete()
        TeamMembership.objects.all().delete()
        Team.objects.all().delete()
        User.objects.all().delete()
        CTFSession.objects.all().delete()
        Category.objects.all().delete()
        SiteSettings.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Data wiped."))

        # ------------------------------------------------------------------ #
        # Site Settings & Session                                             #
        # ------------------------------------------------------------------ #
        SiteSettings.objects.create(is_ctf_paused=False, global_announcement="")

        session = CTFSession.objects.create(
            name="Cyberweek 2026 — Crypto Edition",
            is_active=True,
            scoring_mode=ScoringMode.DYNAMIC.value,
        )

        # ------------------------------------------------------------------ #
        # Users                                                               #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Creating users..."))
        password = make_password("password123")

        User.objects.create(
            username="admin", email="admin@ctfacile.local",
            password=password, role=UserRole.ADMIN.value,
            is_superuser=True, is_staff=True,
        )
        User.objects.create(
            username="prof1", email="prof1@ctfacile.local",
            password=password, role=UserRole.PROF.value,
        )

        students = []
        for i in range(1, 41):
            students.append(User.objects.create(
                username=f"student{i}",
                email=f"student{i}@ctfacile.local",
                password=password,
                role=UserRole.STUDENT.value,
            ))

        self.stdout.write(self.style.SUCCESS(f"Created {len(students)} students + 1 admin + 1 prof."))

        # ------------------------------------------------------------------ #
        # Teams (10 teams x 4 students)                                       #
        # ------------------------------------------------------------------ #
        for i in range(1, 11):
            team = Team.objects.create(name=f"Team {i}", session=session)
            start = (i - 1) * 4
            for j in range(start, min(start + 4, len(students))):
                TeamMembership.objects.create(user=students[j], team=team)

        self.stdout.write(self.style.SUCCESS("10 teams created."))

        # ------------------------------------------------------------------ #
        # Categories                                                          #
        # ------------------------------------------------------------------ #
        cat_crypto    = Category.objects.create(name="Cryptography",  description="Ciphers, encodings, and mathematical crypto")
        cat_web       = Category.objects.create(name="Web Exploitation", description="Web vulnerabilities")
        cat_forensics = Category.objects.create(name="Forensics",     description="Digital forensics and steganography")
        cat_osint     = Category.objects.create(name="OSINT",         description="Open Source Intelligence")

        # ------------------------------------------------------------------ #
        # Elementary Bricks (ChallengeTemplates)                              #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Creating Elementary Bricks..."))

        # --- Base64 ---
        tmpl_b64 = ChallengeTemplate.objects.create(
            name="Base64 Encoding Challenge",
            category=cat_crypto,
            description=(
                "Someone thought encoding was the same as encrypting. "
                "Decode the message below to find the hidden flag."
            ),
            base_docker_image="",
            vulnerability_type="crypto_base64",
        )
        TemplateVariable.objects.create(template=tmpl_b64, key_name="PLAINTEXT_MESSAGE", default_value="The flag is FLAG{base64_not_encryption}", is_required=True)
        TemplateVariable.objects.create(template=tmpl_b64, key_name="FLAG",              default_value="FLAG{base64_not_encryption}",            is_required=True)

        # --- Caesar ---
        tmpl_caesar = ChallengeTemplate.objects.create(
            name="Caesar Cipher",
            category=cat_crypto,
            description="A classic substitution cipher used by Julius Caesar. Decrypt the message using the given shift value.",
            base_docker_image="",
            vulnerability_type="crypto_caesar",
        )
        TemplateVariable.objects.create(template=tmpl_caesar, key_name="PLAINTEXT_MESSAGE", default_value="THE FLAG IS FLAG{et_tu_brute}", is_required=True)
        TemplateVariable.objects.create(template=tmpl_caesar, key_name="SHIFT_AMOUNT",      default_value="7",                             is_required=True)
        TemplateVariable.objects.create(template=tmpl_caesar, key_name="FLAG",              default_value="FLAG{et_tu_brute}",             is_required=True)

        # --- Vigenere ---
        tmpl_vigenere = ChallengeTemplate.objects.create(
            name="Vigenere Cipher",
            category=cat_crypto,
            description=(
                "A polyalphabetic substitution cipher. Unlike Caesar, the shift changes "
                "with each character based on a repeating keyword. "
                "You have the key — decrypt the message."
            ),
            base_docker_image="",
            vulnerability_type="crypto_vigenere",
        )
        TemplateVariable.objects.create(template=tmpl_vigenere, key_name="PLAINTEXT_MESSAGE", default_value="THE SECRET IS FLAG{POLYALPHABETIC_POWER}", is_required=True)
        TemplateVariable.objects.create(template=tmpl_vigenere, key_name="KEY",               default_value="HACK",                                  is_required=True)
        TemplateVariable.objects.create(template=tmpl_vigenere, key_name="FLAG",              default_value="FLAG{polyalphabetic_power}",             is_required=True)

        # --- XOR ---
        tmpl_xor = ChallengeTemplate.objects.create(
            name="Single-Byte XOR Cipher",
            category=cat_crypto,
            description=(
                "A message was encrypted by XOR-ing every byte against the same secret key byte. "
                "The key is unknown — but XOR is symmetric and the keyspace is only 256 values."
            ),
            base_docker_image="",
            vulnerability_type="crypto_xor",
        )
        TemplateVariable.objects.create(template=tmpl_xor, key_name="PLAINTEXT_MESSAGE", default_value="FLAG{xor_is_symmetric}", is_required=True)
        TemplateVariable.objects.create(template=tmpl_xor, key_name="XOR_KEY_HEX",       default_value="42",                    is_required=True)
        TemplateVariable.objects.create(template=tmpl_xor, key_name="FLAG",              default_value="FLAG{xor_is_symmetric}", is_required=True)

        # --- RSA Small N ---
        tmpl_rsa = ChallengeTemplate.objects.create(
            name="RSA — Small N (Textbook)",
            category=cat_crypto,
            description=(
                "Textbook RSA with a dangerously small modulus. "
                "The public key is given. Factor N to recover the private key, then decrypt."
            ),
            base_docker_image="",
            vulnerability_type="crypto_rsa_small",
        )
        TemplateVariable.objects.create(template=tmpl_rsa, key_name="P",             default_value="61",   is_required=True)
        TemplateVariable.objects.create(template=tmpl_rsa, key_name="Q",             default_value="53",   is_required=True)
        TemplateVariable.objects.create(template=tmpl_rsa, key_name="E",             default_value="17",   is_required=True)
        TemplateVariable.objects.create(template=tmpl_rsa, key_name="SECRET_NUMBER", default_value="1337", is_required=True)
        TemplateVariable.objects.create(template=tmpl_rsa, key_name="FLAG",          default_value="FLAG{1337}", is_required=True)

        # --- EOF Stego ---
        tmpl_stego = ChallengeTemplate.objects.create(
            name="EOF Image Steganography",
            category=cat_forensics,
            description="We intercepted this image. The suspect hides data after the end of image files. Find it.",
            base_docker_image="",
            vulnerability_type="forensics_eof_stego",
        )
        TemplateVariable.objects.create(template=tmpl_stego, key_name="FLAG", default_value="FLAG{hidden_in_plain_sight}", is_required=True)

        # --- SQLi (Web) ---
        tmpl_sqli = ChallengeTemplate.objects.create(
            name="SQL Injection — Login Bypass",
            category=cat_web,
            description="A vulnerable login portal. Bypass authentication using SQL injection.",
            base_docker_image="ctfacile/sqli-base:latest",
            vulnerability_type="sqli",
        )
        TemplateVariable.objects.create(template=tmpl_sqli, key_name="FLAG",           default_value="FLAG{sqli_master}",  is_required=True)
        TemplateVariable.objects.create(template=tmpl_sqli, key_name="ADMIN_USERNAME", default_value="admin",              is_required=True)

        self.stdout.write(self.style.SUCCESS("7 Elementary Bricks created."))

        # ------------------------------------------------------------------ #
        # Crypto CTF Skill Tree                                               #
        # All crypto challenges built via ChallengeBuilderService so that     #
        # ciphertexts are auto-generated and embedded in descriptions.        #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Building crypto skill tree via the builder engine..."))

        # --- Level 1: Tutorial (manual, no template) ---
        tutorial = Challenge.objects.create(
            title="Welcome: Read the Rules",
            session=session, category=cat_osint,
            description=(
                "Welcome to Cyberweek 2026 — Crypto Edition!\n\n"
                "Read the competition rules carefully. "
                "The flag is hidden in plain sight on this page.\n\n"
                "**Flag format:** `FLAG{...}`"
            ),
            base_points=25,
            challenge_type="STATIC",
            flag_hash=sha256("FLAG{welcome_to_cyberweek_2026}"),
            is_tutorial=True,
            is_entry_node=True,
        )

        # --- Level 1: Base64 (entry node, built via builder) ---
        b64_challenge = ChallengeBuilderService.build_challenge(
            session_id=session.id,
            category_id=cat_crypto.id,
            template_id=tmpl_b64.id,
            title="Crypto 1: Base64 Bonanza",
            base_points=50,
            custom_params_dict={
                "PLAINTEXT_MESSAGE": "The flag is FLAG{base64_not_encryption}",
                "FLAG": "FLAG{base64_not_encryption}",
            },
            custom_description=(
                "Someone thought encoding was the same as encrypting. "
                "They sent us this message thinking it was secret.\n\n"
                "Decode it to find the flag. Tools: CyberChef, Python `base64` module, or `base64 -d` in a terminal."
            ),
        )
        b64_challenge.is_entry_node = True
        b64_challenge.save()

        # --- Level 2: Caesar (prereq: Base64) ---
        caesar_challenge = ChallengeBuilderService.build_challenge(
            session_id=session.id,
            category_id=cat_crypto.id,
            template_id=tmpl_caesar.id,
            title="Crypto 2: Et Tu, Brute?",
            base_points=100,
            custom_params_dict={
                "PLAINTEXT_MESSAGE": "THE FLAG IS FLAG{et_tu_brute}",
                "SHIFT_AMOUNT": "7",
                "FLAG": "FLAG{et_tu_brute}",
            },
            custom_description=(
                "Julius Caesar used a simple substitution cipher to protect his messages. "
                "Each letter is shifted by the same fixed amount.\n\n"
                "The shift value is given below. Decrypt the ciphertext to find the flag.\n\n"
                "*Hint: Only alphabetical characters are shifted. "
                "Spaces, braces, and underscores are unchanged.*"
            ),
        )
        ChallengePrerequisite.objects.create(target_challenge=caesar_challenge, required_challenge=b64_challenge)

        # --- Level 3: Vigenere (prereq: Caesar) ---
        vigenere_challenge = ChallengeBuilderService.build_challenge(
            session_id=session.id,
            category_id=cat_crypto.id,
            template_id=tmpl_vigenere.id,
            title="Crypto 3: The Vigenere Vendetta",
            base_points=200,
            custom_params_dict={
                "PLAINTEXT_MESSAGE": "THE SECRET IS FLAG{POLYALPHABETIC_POWER}",
                "KEY": "HACK",
                "FLAG": "FLAG{polyalphabetic_power}",
            },
            custom_description=(
                "Vigenere improves on Caesar by using a **keyword** instead of a fixed shift. "
                "Each letter of the keyword defines the shift for the corresponding plaintext character.\n\n"
                "The key repeats for the length of the message. "
                "You have the key — now decrypt.\n\n"
                "*Hint: Submit the flag in lowercase as it appears after decryption.*"
            ),
        )
        ChallengePrerequisite.objects.create(target_challenge=vigenere_challenge, required_challenge=caesar_challenge)

        # --- Level 4: XOR (prereq: Vigenere) ---
        xor_challenge = ChallengeBuilderService.build_challenge(
            session_id=session.id,
            category_id=cat_crypto.id,
            template_id=tmpl_xor.id,
            title="Crypto 4: XOR Files",
            base_points=300,
            custom_params_dict={
                "PLAINTEXT_MESSAGE": "FLAG{xor_is_symmetric}",
                "XOR_KEY_HEX": "42",
                "FLAG": "FLAG{xor_is_symmetric}",
            },
            custom_description=(
                "A message was encrypted by XOR-ing every byte with the same secret key byte.\n\n"
                "The ciphertext is given as hex bytes below. "
                "The key is **not** provided — you must find it yourself.\n\n"
                "**Python solution skeleton:**\n"
                "```python\n"
                "cipher_hex = '04 0e 03 ...'\n"
                "cipher_bytes = bytes(int(x, 16) for x in cipher_hex.split())\n"
                "for key in range(256):\n"
                "    attempt = bytes(b ^ key for b in cipher_bytes)\n"
                "    if attempt.startswith(b'FLAG'):\n"
                "        print(f'Key={key:#x}: {attempt}')\n"
                "```"
            ),
        )
        ChallengePrerequisite.objects.create(target_challenge=xor_challenge, required_challenge=vigenere_challenge)

        # --- Level 5: RSA (prereq: XOR) ---
        rsa_challenge = ChallengeBuilderService.build_challenge(
            session_id=session.id,
            category_id=cat_crypto.id,
            template_id=tmpl_rsa.id,
            title="Crypto 5: RSA — Factor Me If You Can",
            base_points=500,
            custom_params_dict={
                "P": "61",
                "Q": "53",
                "E": "17",
                "SECRET_NUMBER": "1337",
                "FLAG": "FLAG{1337}",
            },
            custom_description=(
                "Textbook RSA. The modulus N is suspiciously small — small enough to factor.\n\n"
                "**Your mission:**\n"
                "1. Factor N to find p and q\n"
                "2. Compute φ(N) = (p−1)(q−1)\n"
                "3. Find d = modular inverse of e mod φ(N)\n"
                "4. Decrypt: M = C^d mod N\n"
                "5. The flag is `FLAG{M}` where M is the decrypted number\n\n"
                "**Python one-liner to find d:**\n"
                "```python\n"
                "from sympy import mod_inverse\n"
                "d = mod_inverse(e, phi)\n"
                "M = pow(C, d, N)\n"
                "print(f'FLAG{{{M}}}')\n"
                "```"
            ),
        )
        ChallengePrerequisite.objects.create(target_challenge=rsa_challenge, required_challenge=xor_challenge)

        # --- Forensics Bonus: EOF Stego (entry node, standalone) ---
        stego_challenge = ChallengeBuilderService.build_challenge(
            session_id=session.id,
            category_id=cat_forensics.id,
            template_id=tmpl_stego.id,
            title="Forensics 1: Something is Off",
            base_points=150,
            custom_params_dict={
                "FLAG": "FLAG{hidden_in_plain_sight}",
            },
            custom_description=(
                "We intercepted this image from a suspect's device. "
                "Intelligence suggests they hide messages *after* the end of image files.\n\n"
                "**Download the attachment and try:**\n"
                "```bash\n"
                "strings evidence.png\n"
                "# or\n"
                "xxd evidence.png | tail -5\n"
                "# or\n"
                "binwalk evidence.png\n"
                "```"
            ),
        )
        stego_challenge.is_entry_node = True
        stego_challenge.save()

        self.stdout.write(self.style.SUCCESS("Skill tree built: 7 challenges, 4 prerequisites."))

        # ------------------------------------------------------------------ #
        # Achievements                                                        #
        # ------------------------------------------------------------------ #
        Achievement.objects.create(
            title="First Blood",
            description="First team to solve any challenge in the session.",
            trigger_type=TriggerType.FIRST_BLOOD.value,
            threshold_value=1,
            is_secret=False,
            icon_reference="first_blood.json",
        )
        Achievement.objects.create(
            title="Crypto Padawan",
            description="Solve 3 crypto challenges.",
            trigger_type=TriggerType.SOLVE_STREAK.value,
            threshold_value=3,
            is_secret=False,
            icon_reference="padawan.json",
        )
        Achievement.objects.create(
            title="RSA Slayer",
            description="Solve the RSA challenge.",
            trigger_type=TriggerType.FIRST_BLOOD.value,
            threshold_value=1,
            is_secret=False,
            icon_reference="rsa_slayer.json",
        )
        Achievement.objects.create(
            title="Persistent",
            description="Submit 20 wrong flags. Keep going.",
            trigger_type=TriggerType.ATTEMPT_COUNT.value,
            threshold_value=20,
            is_secret=True,
            icon_reference="persistent.json",
        )

        # ------------------------------------------------------------------ #
        # Summary                                                             #
        # ------------------------------------------------------------------ #
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write(self.style.SUCCESS("  CTFacile — Crypto Edition seeded successfully!"))
        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write("  Session  : Cyberweek 2026 — Crypto Edition")
        self.stdout.write("  Accounts : admin / prof1 / student1..40  (password: password123)")
        self.stdout.write("  Teams    : 10 teams x 4 students")
        self.stdout.write("  Bricks   : 7 Elementary Bricks (usable in the builder UI)")
        self.stdout.write("  Challenges: 7 (2 entry nodes, 4 prerequisites, 1 standalone)")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("  Flags (all generated by the builder engine):"))
        self.stdout.write("    Welcome          → FLAG{welcome_to_cyberweek_2026}")
        self.stdout.write("    Crypto 1 Base64  → FLAG{base64_not_encryption}")
        self.stdout.write("    Crypto 2 Caesar  → FLAG{et_tu_brute}")
        self.stdout.write("    Crypto 3 Vigenere→ FLAG{polyalphabetic_power}")
        self.stdout.write("    Crypto 4 XOR     → FLAG{xor_is_symmetric}")
        self.stdout.write("    Crypto 5 RSA     → FLAG{1337}")
        self.stdout.write("    Forensics 1 Stego→ FLAG{hidden_in_plain_sight}")
        self.stdout.write(self.style.SUCCESS("=" * 65))
        self.stdout.write("")
        self.stdout.write("  Run:  docker-compose exec web python manage.py seed_db")
