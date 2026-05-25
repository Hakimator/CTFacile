"""
Management command: patch_sqli_image
-------------------------------------
Updates the ChallengeTemplate and all deployed Challenges that use the
SQL Injection template to point at the real ctfacile/sqli-base:latest image.

Run after building the image with challenge_images/sqli-login/build.sh:

    docker compose exec web python manage.py patch_sqli_image
"""

from django.core.management.base import BaseCommand
from core.models import ChallengeTemplate, Challenge


IMAGE_TAG     = "ctfacile/sqli-base:latest"
TEMPLATE_NAME = "SQL Injection — Login Bypass"


class Command(BaseCommand):
    help = "Patch the SQLi ChallengeTemplate and deployed Challenges to use the real Docker image."

    def handle(self, *args, **options):
        # ── 1. Update the template ────────────────────────────────────────────
        try:
            tmpl = ChallengeTemplate.objects.get(name=TEMPLATE_NAME)
        except ChallengeTemplate.DoesNotExist:
            self.stderr.write(self.style.ERROR(
                f"ChallengeTemplate '{TEMPLATE_NAME}' not found. "
                "Run seed_db first."
            ))
            return

        if tmpl.base_docker_image == IMAGE_TAG:
            self.stdout.write(self.style.WARNING(
                f"Template already set to '{IMAGE_TAG}' — no change needed."
            ))
        else:
            old = tmpl.base_docker_image
            tmpl.base_docker_image = IMAGE_TAG
            tmpl.save(update_fields=["base_docker_image"])
            self.stdout.write(self.style.SUCCESS(
                f"✓ Template '{TEMPLATE_NAME}': base_docker_image "
                f"'{old}' → '{IMAGE_TAG}'"
            ))

        # ── 2. Update all deployed challenges built from this template ────────
        challenges = Challenge.objects.filter(template=tmpl)
        updated = 0
        for ch in challenges:
            if ch.docker_image_tag != IMAGE_TAG:
                ch.docker_image_tag = IMAGE_TAG
                ch.save(update_fields=["docker_image_tag"])
                updated += 1
                self.stdout.write(f"  ✓ Challenge '{ch.title}' (id={ch.id}) patched.")

        if updated == 0:
            self.stdout.write("  (no deployed challenges needed patching)")
        else:
            self.stdout.write(self.style.SUCCESS(
                f"✓ {updated} challenge(s) updated."
            ))

        self.stdout.write(self.style.SUCCESS(
            "\nDone. Respawn any active instances to pick up the new image."
        ))
