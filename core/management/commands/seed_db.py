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


def sha256(flag: str) -> str:
    """Helper: hash a plaintext flag the same way FlagValidationService does."""
    return hashlib.sha256(flag.encode("utf-8")).hexdigest()


class Command(BaseCommand):
    help = "Flushes the database and seeds it with realistic CTF data for testing."

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("Wiping existing data..."))

        # Wipe in strict reverse-dependency order so FK constraints are satisfied
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
        # Site Settings (Singleton)                                           #
        # ------------------------------------------------------------------ #
        SiteSettings.objects.create(is_ctf_paused=False, global_announcement="")

        # ------------------------------------------------------------------ #
        # CTF Session                                                         #
        # ------------------------------------------------------------------ #
        session = CTFSession.objects.create(
            name="Cyberweek 2026",
            is_active=True,
            scoring_mode=ScoringMode.DYNAMIC.value,
        )

        # ------------------------------------------------------------------ #
        # Users                                                               #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Creating users..."))
        password = make_password("password123")

        admin1 = User.objects.create(
            username="admin", email="admin@ctfacile.local",
            password=password, role=UserRole.ADMIN.value,
            is_superuser=True, is_staff=True,
        )
        admin2 = User.objects.create(
            username="admin2", email="admin2@ctfacile.local",
            password=password, role=UserRole.ADMIN.value,
            is_superuser=True, is_staff=True,
        )
        prof1 = User.objects.create(
            username="prof1", email="prof1@ctfacile.local",
            password=password, role=UserRole.PROF.value,
        )
        prof2 = User.objects.create(
            username="prof2", email="prof2@ctfacile.local",
            password=password, role=UserRole.PROF.value,
        )

        students = []
        for i in range(1, 101):
            students.append(User.objects.create(
                username=f"student{i}",
                email=f"student{i}@ctfacile.local",
                password=password,
                role=UserRole.STUDENT.value,
            ))

        self.stdout.write(self.style.SUCCESS(f"Created {len(students)} students + 2 admins + 2 profs."))

        # ------------------------------------------------------------------ #
        # Teams (25 teams × 4 students)                                       #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Creating teams..."))
        for i in range(1, 26):
            team = Team.objects.create(name=f"Team {i}", session=session)
            start = (i - 1) * 4
            for j in range(start, start + 4):
                if j < len(students):
                    TeamMembership.objects.create(user=students[j], team=team)

        self.stdout.write(self.style.SUCCESS("25 teams created."))

        # ------------------------------------------------------------------ #
        # Categories                                                          #
        # ------------------------------------------------------------------ #
        cat_osint    = Category.objects.create(name="OSINT",                  description="Open Source Intelligence")
        cat_web      = Category.objects.create(name="Web Exploitation",        description="Web vulnerabilities and exploits")
        cat_crypto   = Category.objects.create(name="Cryptography",            description="Ciphers, hashes, and crypto flaws")
        cat_rev      = Category.objects.create(name="Reverse Engineering",     description="Disassembly and binary analysis")
        cat_forensics= Category.objects.create(name="Forensics",               description="Digital forensics and memory analysis")
        cat_pwn      = Category.objects.create(name="Pwn (Binary Exploitation)", description="Buffer overflows and ROP chains")

        # ------------------------------------------------------------------ #
        # Elementary Bricks (ChallengeTemplates)                              #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Creating Elementary Bricks..."))

        # SQL Injection
        tmpl_sqli = ChallengeTemplate.objects.create(
            name="Basic SQL Injection (Login Bypass)",
            category=cat_web,
            description=(
                "A deliberately vulnerable login portal. "
                "Bypass authentication using classic SQL injection techniques.\n\n"
                "**Objective:** Log in as the admin without knowing the password."
            ),
            base_docker_image="ctfacile/sqli-base:latest",
            vulnerability_type="sqli",
        )
        TemplateVariable.objects.create(template=tmpl_sqli, key_name="FLAG",           default_value="FLAG{sqli_master}",  is_required=True)
        TemplateVariable.objects.create(template=tmpl_sqli, key_name="ADMIN_USERNAME", default_value="admin",              is_required=True)
        TemplateVariable.objects.create(template=tmpl_sqli, key_name="DB_NAME",        default_value="ctf_users",          is_required=False)

        # XSS
        tmpl_xss = ChallengeTemplate.objects.create(
            name="Stored XSS (Admin Bot Cookie Theft)",
            category=cat_web,
            description=(
                "A public guestbook that an admin bot visits every minute. "
                "Inject a JavaScript payload to steal the bot's session cookie — "
                "the flag is stored in it.\n\n"
                "**Objective:** Exfiltrate the admin cookie."
            ),
            base_docker_image="ctfacile/xss-base:latest",
            vulnerability_type="xss",
        )
        TemplateVariable.objects.create(template=tmpl_xss, key_name="FLAG",                  default_value="FLAG{xss_c00kie_m0nster}", is_required=True)
        TemplateVariable.objects.create(template=tmpl_xss, key_name="BOT_POLL_RATE_SECONDS", default_value="60",                      is_required=False)

        # Caesar Cipher (Static — no Docker, triggers cipher enrichment in builder)
        tmpl_caesar = ChallengeTemplate.objects.create(
            name="Caesar Cipher Decoder",
            category=cat_crypto,
            description="Decrypt the following message to find the flag.",
            base_docker_image="",
            vulnerability_type="crypto_caesar",
        )
        TemplateVariable.objects.create(template=tmpl_caesar, key_name="PLAINTEXT_MESSAGE", default_value="THE SECRET IS FLAG{caesar_salad}", is_required=True)
        TemplateVariable.objects.create(template=tmpl_caesar, key_name="SHIFT_AMOUNT",      default_value="3",                              is_required=True)
        TemplateVariable.objects.create(template=tmpl_caesar, key_name="FLAG",              default_value="FLAG{caesar_salad}",             is_required=True)

        # EOF Steganography (Static — generates a PNG attachment)
        tmpl_stego = ChallengeTemplate.objects.create(
            name="EOF Image Steganography",
            category=cat_forensics,
            description=(
                "We intercepted this image from a suspect's hard drive. "
                "Intelligence suggests they hide messages *after* the end of image files.\n\n"
                "**Objective:** Extract the hidden data appended beyond the IEND chunk."
            ),
            base_docker_image="",
            vulnerability_type="forensics_eof_stego",
        )
        TemplateVariable.objects.create(template=tmpl_stego, key_name="FLAG", default_value="FLAG{hidden_in_plain_sight}", is_required=True)

        # LFI (new)
        tmpl_lfi = ChallengeTemplate.objects.create(
            name="Local File Inclusion (LFI)",
            category=cat_web,
            description=(
                "A PHP application that naively includes files based on a URL parameter. "
                "Read `/etc/passwd` first, then find the flag file.\n\n"
                "**Objective:** Use path traversal to read `flag.txt` from the server."
            ),
            base_docker_image="ctfacile/lfi-base:latest",
            vulnerability_type="lfi",
        )
        TemplateVariable.objects.create(template=tmpl_lfi, key_name="FLAG",      default_value="FLAG{lfi_path_traversal}", is_required=True)
        TemplateVariable.objects.create(template=tmpl_lfi, key_name="FLAG_PATH", default_value="/var/www/secret/flag.txt", is_required=False)

        self.stdout.write(self.style.SUCCESS("5 Elementary Bricks created."))

        # ------------------------------------------------------------------ #
        # Challenges (Skill Tree)                                             #
        # All flag values are real — submit these exact strings to solve.     #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Creating challenge skill tree..."))

        # --- Tutorial / Entry ---
        tutorial = Challenge.objects.create(
            title="Zero-to-Hacker: Kali Setup",
            session=session, category=cat_osint,
            description=(
                "Welcome! Your first mission is simple: get your environment running.\n\n"
                "The flag is hidden in the course syllabus PDF on the homepage. "
                "Download it, search for the flag format `FLAG{...}`, and submit it below."
            ),
            base_points=50,
            challenge_type="STATIC",
            flag_hash=sha256("FLAG{welcome_to_cyberweek_2026}"),
            is_tutorial=True,
            is_entry_node=True,
        )

        # --- OSINT ---
        osint_101 = Challenge.objects.create(
            title="OSINT 101: Google Dorking",
            session=session, category=cat_osint,
            description=(
                "Using only Google, find the email address of the CTO of the fictional company "
                "`AcmeCorp Technologies`. Their website is `acmecorp-ctf.example.com`.\n\n"
                "The flag format is `FLAG{firstname.lastname@acmecorp.com}`."
            ),
            base_points=100,
            challenge_type="STATIC",
            flag_hash=sha256("FLAG{john.doe@acmecorp.com}"),
            is_entry_node=True,
        )

        # --- Web Branch ---
        web_101 = Challenge.objects.create(
            title="Web 101: SQL Injection Login Bypass",
            session=session, category=cat_web,
            description=(
                "A login portal is protected by a SQL query that looks like:\n\n"
                "```sql\nSELECT * FROM users WHERE username='$u' AND password='$p'\n```\n\n"
                "**Objective:** Bypass authentication and log in as `admin`. "
                "The flag will be displayed on the admin dashboard."
            ),
            base_points=100,
            challenge_type="CONTAINER",
            flag_hash=sha256("FLAG{sqli_bypass_is_trivial}"),
            docker_image_tag="nginxdemos/hello",
            internal_port=80,
            is_entry_node=True,
        )

        web_102 = Challenge.objects.create(
            title="Web 102: Stored XSS Cookie Theft",
            session=session, category=cat_web,
            description=(
                "A public guestbook is visited by an admin bot every 60 seconds. "
                "The bot's cookie contains the flag.\n\n"
                "**Objective:** Post a malicious `<script>` tag that exfiltrates "
                "the admin cookie to your listener."
            ),
            base_points=200,
            challenge_type="CONTAINER",
            flag_hash=sha256("FLAG{xss_stole_the_cookie}"),
            docker_image_tag="nginxdemos/hello",
            internal_port=80,
        )
        ChallengePrerequisite.objects.create(target_challenge=web_102, required_challenge=web_101)

        web_201 = Challenge.objects.create(
            title="Web 201: Local File Inclusion",
            session=session, category=cat_web,
            description=(
                "A PHP site includes files via `?page=about`. Try substituting "
                "path traversal sequences to read server-side files.\n\n"
                "**Objective:** Read `/flag.txt` via LFI."
            ),
            base_points=250,
            challenge_type="CONTAINER",
            flag_hash=sha256("FLAG{lfi_../../etc/flag}"),
            docker_image_tag="nginxdemos/hello",
            internal_port=80,
        )
        ChallengePrerequisite.objects.create(target_challenge=web_201, required_challenge=web_102)

        # --- Crypto Branch ---
        crypto_101 = Challenge.objects.create(
            title="Crypto 101: Caesar Salad",
            session=session, category=cat_crypto,
            description=(
                "Et tu, Brute?\n\n"
                "Decrypt the following message (shift = 13):\n\n"
                "`SYNT{pnrfne_fnynq}`\n\n"
                "**Hint:** ROT13 is just Caesar with shift=13."
            ),
            base_points=75,
            challenge_type="STATIC",
            flag_hash=sha256("FLAG{caesar_salad}"),
            is_entry_node=True,
        )

        crypto_102 = Challenge.objects.create(
            title="Crypto 102: Base64 is not Encryption",
            session=session, category=cat_crypto,
            description=(
                "Someone thought encoding was the same as encrypting. Decode this:\n\n"
                "`RkxBR3tiYXNlNjRfaXNfbm90X2VuY3J5cHRpb259`"
            ),
            base_points=50,
            challenge_type="STATIC",
            flag_hash=sha256("FLAG{base64_is_not_encryption}"),
        )
        ChallengePrerequisite.objects.create(target_challenge=crypto_102, required_challenge=crypto_101)

        crypto_201 = Challenge.objects.create(
            title="Crypto 201: RSA — Small N",
            session=session, category=cat_crypto,
            description=(
                "RSA public key: `n=3233, e=17`. The ciphertext is `c=2790`.\n\n"
                "N is small enough to factor by hand. Find `p` and `q`, compute `d`, "
                "decrypt `c` to get the ASCII flag character.\n\n"
                "The full flag wraps the decrypted value: `FLAG{<value>}`."
            ),
            base_points=300,
            challenge_type="STATIC",
            flag_hash=sha256("FLAG{65}"),
        )
        ChallengePrerequisite.objects.create(target_challenge=crypto_201, required_challenge=crypto_102)

        # --- Forensics Branch ---
        forensics_101 = Challenge.objects.create(
            title="Forensics 101: Strings in a Binary",
            session=session, category=cat_forensics,
            description=(
                "Download the binary below and run `strings` on it. "
                "Something suspicious is hiding in the printable characters.\n\n"
                "**Objective:** Extract the embedded flag."
            ),
            base_points=75,
            challenge_type="STATIC",
            flag_hash=sha256("FLAG{strings_are_powerful}"),
            is_entry_node=True,
        )

        forensics_102 = Challenge.objects.create(
            title="Forensics 102: EOF Steganography",
            session=session, category=cat_forensics,
            description=(
                "We intercepted this image. Intelligence suggests data is hidden "
                "*after* the IEND chunk — beyond where most image viewers stop reading.\n\n"
                "**Objective:** Use `xxd`, `binwalk`, or `dd` to extract the appended payload."
            ),
            base_points=150,
            challenge_type="STATIC",
            flag_hash=sha256("FLAG{hidden_in_plain_sight}"),
        )
        ChallengePrerequisite.objects.create(target_challenge=forensics_102, required_challenge=forensics_101)

        # --- Boss Node ---
        boss_rce = Challenge.objects.create(
            title="THE FINAL BOSS: Remote Code Execution",
            session=session, category=cat_pwn,
            description=(
                "The target server runs a custom service on port 1337. "
                "It processes user input without sanitization.\n\n"
                "**Objective:** Chain your web and crypto knowledge to pop a reverse shell "
                "and read `/root/flag.txt`.\n\n"
                "*This challenge requires completing both the Web and Crypto branches.*"
            ),
            base_points=1000,
            challenge_type="CONTAINER",
            flag_hash=sha256("FLAG{r00t_the_planet}"),
            docker_image_tag="nginxdemos/hello",
            internal_port=80,
        )
        ChallengePrerequisite.objects.create(target_challenge=boss_rce, required_challenge=web_201)
        ChallengePrerequisite.objects.create(target_challenge=boss_rce, required_challenge=crypto_201)

        self.stdout.write(self.style.SUCCESS("Skill tree created (11 challenges, 7 prerequisites)."))

        # ------------------------------------------------------------------ #
        # Achievements                                                        #
        # ------------------------------------------------------------------ #
        self.stdout.write(self.style.WARNING("Creating achievements..."))

        Achievement.objects.create(
            title="First Blood",
            description="First team in the session to solve any challenge.",
            trigger_type=TriggerType.FIRST_BLOOD.value,
            threshold_value=1,
            is_secret=False,
            icon_reference="first_blood.json",
        )
        Achievement.objects.create(
            title="Speed Runner",
            description="Solve 3 challenges in a row without a failed attempt in between.",
            trigger_type=TriggerType.SOLVE_STREAK.value,
            threshold_value=3,
            is_secret=False,
            icon_reference="speed_runner.json",
        )
        Achievement.objects.create(
            title="Persistent",
            description="Submit 50 incorrect flags and keep going.",
            trigger_type=TriggerType.ATTEMPT_COUNT.value,
            threshold_value=50,
            is_secret=True,
            icon_reference="persistent.json",
        )
        Achievement.objects.create(
            title="The Boss Slayer",
            description="Solve the Final Boss challenge.",
            trigger_type=TriggerType.FIRST_BLOOD.value,
            threshold_value=1,
            is_secret=False,
            icon_reference="boss_slayer.json",
        )

        self.stdout.write(self.style.SUCCESS("4 achievements created."))

        # ------------------------------------------------------------------ #
        # Summary                                                             #
        # ------------------------------------------------------------------ #
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("  CTFacile database seeded successfully!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  Session  : Cyberweek 2026 (DYNAMIC scoring)")
        self.stdout.write(f"  Users    : admin / admin2 / prof1 / prof2 / student1..100")
        self.stdout.write(f"  Password : password123 (all accounts)")
        self.stdout.write(f"  Teams    : 25 teams × 4 students")
        self.stdout.write(f"  Bricks   : 5 Elementary Bricks (templates)")
        self.stdout.write(f"  Challenges: 11 (4 entry nodes, 1 boss, 7 prerequisites)")
        self.stdout.write(f"  Achievements: 4")
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("  All flags are real — submit them as-is to test the engine:"))
        self.stdout.write(f"    Tutorial   → FLAG{{welcome_to_cyberweek_2026}}")
        self.stdout.write(f"    OSINT 101  → FLAG{{john.doe@acmecorp.com}}")
        self.stdout.write(f"    Web 101    → FLAG{{sqli_bypass_is_trivial}}")
        self.stdout.write(f"    Web 102    → FLAG{{xss_stole_the_cookie}}")
        self.stdout.write(f"    Web 201    → FLAG{{lfi_../../etc/flag}}")
        self.stdout.write(f"    Crypto 101 → FLAG{{caesar_salad}}")
        self.stdout.write(f"    Crypto 102 → FLAG{{base64_is_not_encryption}}")
        self.stdout.write(f"    Crypto 201 → FLAG{{65}}")
        self.stdout.write(f"    Forensics 101 → FLAG{{strings_are_powerful}}")
        self.stdout.write(f"    Forensics 102 → FLAG{{hidden_in_plain_sight}}")
        self.stdout.write(f"    Final Boss → FLAG{{r00t_the_planet}}")
        self.stdout.write(self.style.SUCCESS("=" * 60))
