from django.core.management.base import BaseCommand
from applications.utils import trigger_swiftmassive_event
import os

class Command(BaseCommand):
    help = 'Tests the Swiftmassive API connection'

    def add_arguments(self, parser):
        parser.add_argument('email', type=str, help='The email to send the test to')

    def handle(self, *args, **options):
        email = options['email']
        self.stdout.write(f"Attempting to send test event to {email}...")

        # Test data mirroring your Welcome Email logic
        test_data = {
            "first_name": "TestUser",
            "login_url": "https://mpgss-ycle.onrender.com/login/"
        }

        try:
            success = trigger_swiftmassive_event(
                email=email,
                event_name="welcome_email",
                data=test_data
            )
            if success:
                self.stdout.write(self.style.SUCCESS(f"Successfully triggered 'welcome_email' for {email}"))
            else:
                self.stdout.write(self.style.ERROR("API call failed. Check your logs."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {str(e)}"))