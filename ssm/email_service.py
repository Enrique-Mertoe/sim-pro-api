import os
import secrets

import resend
from django.template.loader import render_to_string
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

# Initialize Resend with API key from environment
resend.api_key = getattr(settings, "RESEND_API_KEY")


def generate_dynamic_sender(domain: str):
    unique_id = secrets.token_urlsafe(8)
    return f"no-reply-s-{unique_id}@{domain}"


class EmailService:
    DOMAIN = "mail.nagelecommunication.com"

    @staticmethod
    def send_password_reset_email(email: str, reset_token: str, reset_link: str):
        """Send password reset email using Resend"""
        try:
            # Render HTML template
            html_content = render_to_string('email/password_reset.html', {
                'email': email,
                'reset_link': reset_link,
                'reset_token': reset_token
            })

            # Render text template
            text_content = render_to_string('email/password_reset.txt', {
                'email': email,
                'reset_link': reset_link,
                'reset_token': reset_token
            })

            # Send email via Resend
            from_email = generate_dynamic_sender(EmailService.DOMAIN)
            params = {
                "from": f"SSM Support <{from_email}>",
                "to": [email],
                "subject": "Reset Your Password",
                "html": html_content,
                "text": text_content,
            }

            response = resend.Emails.send(params)
            logger.info(f"Password reset email sent to {email}. Resend ID: {response.get('id')}")
            return True

        except Exception as e:
            logger.error(f"Failed to send password reset email to {email}: {str(e)}")
            return False

    @staticmethod
    def send_email_verification(email: str, verification_token: str, verification_link: str, user_name: str = None):
        """Send email verification email using Resend"""
        try:
            # Render HTML template
            html_content = render_to_string('email/email_verification.html', {
                'email': email,
                'verification_link': verification_link,
                'verification_token': verification_token,
                'user_name': user_name or email
            })

            # Render text template
            text_content = render_to_string('email/email_verification.txt', {
                'email': email,
                'verification_link': verification_link,
                'verification_token': verification_token,
                'user_name': user_name or email
            })

            # Send email via Resend
            params = {
                "from": f"SSM Support<{getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@kaigates.com')}>",
                "to": [email],
                "subject": "Verify Your Email Address",
                "html": html_content,
                "text": text_content,
            }

            response = resend.Emails.send(params)
            logger.info(f"Email verification sent to {email}. Resend ID: {response.get('id')}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email verification to {email}: {str(e)}")
            return False
