"""
Settings-related RPC functions
"""
from ..models import UserSettings, User


def get_user_settings(user):
    """Get user settings or create default if not exists"""
    try:
        settings = UserSettings.objects.filter(user=user).first()

        if not settings:
            # Create default settings
            settings = UserSettings.objects.create(
                user=user,
                email_notifications=True,
                sms_notifications=True,
                push_notifications=True,
                marketing_emails=False,
                security_alerts=True,
                report_notifications=True,
                team_updates=True,
                profile_visibility='team_only',
                show_email=False,
                show_phone=False,
                data_sharing=False,
                activity_tracking=True,
                two_factor_enabled=False,
                session_timeout=30,
                login_alerts=True,
                language='en',
                timezone='Africa/Nairobi',
                date_format='DD/MM/YYYY',
                theme='auto'
            )

        return {
            'success': True,
            'settings': {
                'id': str(settings.id),
                'user_id': str(settings.user.id),
                # Notification preferences
                'email_notifications': settings.email_notifications,
                'sms_notifications': settings.sms_notifications,
                'push_notifications': settings.push_notifications,
                'marketing_emails': settings.marketing_emails,
                'security_alerts': settings.security_alerts,
                'report_notifications': settings.report_notifications,
                'team_updates': settings.team_updates,
                # Privacy settings
                'profile_visibility': settings.profile_visibility,
                'show_email': settings.show_email,
                'show_phone': settings.show_phone,
                'data_sharing': settings.data_sharing,
                'activity_tracking': settings.activity_tracking,
                # Security settings
                'two_factor_enabled': settings.two_factor_enabled,
                'session_timeout': settings.session_timeout,
                'login_alerts': settings.login_alerts,
                # Account settings
                'language': settings.language,
                'timezone': settings.timezone,
                'date_format': settings.date_format,
                'theme': settings.theme,
            }
        }
    except Exception as e:
        raise ValueError(f"Error getting user settings: {str(e)}")


def update_notification_preferences(user, **preferences):
    """Update notification preferences"""
    try:
        settings, created = UserSettings.objects.get_or_create(user=user)

        # Update only notification-related fields
        notification_fields = [
            'email_notifications', 'sms_notifications', 'push_notifications',
            'marketing_emails', 'security_alerts', 'report_notifications', 'team_updates'
        ]

        for field in notification_fields:
            if field in preferences:
                setattr(settings, field, preferences[field])

        settings.save()

        return {
            'success': True,
            'message': 'Notification preferences updated successfully'
        }
    except Exception as e:
        raise ValueError(f"Error updating notification preferences: {str(e)}")


def update_privacy_preferences(user, **preferences):
    """Update privacy preferences"""
    try:
        settings, created = UserSettings.objects.get_or_create(user=user)

        # Update only privacy-related fields
        privacy_fields = [
            'profile_visibility', 'show_email', 'show_phone',
            'data_sharing', 'activity_tracking'
        ]

        for field in privacy_fields:
            if field in preferences:
                setattr(settings, field, preferences[field])

        settings.save()

        return {
            'success': True,
            'message': 'Privacy preferences updated successfully'
        }
    except Exception as e:
        raise ValueError(f"Error updating privacy preferences: {str(e)}")


def update_security_settings(user, **settings_data):
    """Update security settings"""
    try:
        settings, created = UserSettings.objects.get_or_create(user=user)

        # Update only security-related fields
        security_fields = ['two_factor_enabled', 'session_timeout', 'login_alerts']

        for field in security_fields:
            if field in settings_data:
                setattr(settings, field, settings_data[field])

        settings.save()

        return {
            'success': True,
            'message': 'Security settings updated successfully'
        }
    except Exception as e:
        raise ValueError(f"Error updating security settings: {str(e)}")


def update_account_preferences(user, **preferences):
    """Update account preferences"""
    try:
        settings, created = UserSettings.objects.get_or_create(user=user)

        # Update only account-related fields
        account_fields = ['language', 'timezone', 'date_format', 'theme']

        for field in account_fields:
            if field in preferences:
                setattr(settings, field, preferences[field])

        settings.save()

        return {
            'success': True,
            'message': 'Account preferences updated successfully'
        }
    except Exception as e:
        raise ValueError(f"Error updating account preferences: {str(e)}")


def change_password(user, current_password, new_password):
    """Change user password"""
    try:
        # Verify current password
        if not user.check_password(current_password):
            return {
                'success': False,
                'error': 'Current password is incorrect'
            }

        # Set new password
        user.set_password(new_password)
        user.save()

        return {
            'success': True,
            'message': 'Password changed successfully'
        }
    except Exception as e:
        raise ValueError(f"Error changing password: {str(e)}")


def enable_two_factor_auth(user):
    """Enable 2FA for user"""
    try:
        settings, created = UserSettings.objects.get_or_create(user=user)
        settings.two_factor_enabled = True
        settings.save()

        # TODO: Generate and return 2FA secret/QR code

        return {
            'success': True,
            'message': '2FA enabled successfully',
            # 'secret': secret,
            # 'qr_code': qr_code_url
        }
    except Exception as e:
        raise ValueError(f"Error enabling 2FA: {str(e)}")


def disable_two_factor_auth(user):
    """Disable 2FA for user"""
    try:
        settings = UserSettings.objects.filter(user=user).first()
        if settings:
            settings.two_factor_enabled = False
            settings.save()

        return {
            'success': True,
            'message': '2FA disabled successfully'
        }
    except Exception as e:
        raise ValueError(f"Error disabling 2FA: {str(e)}")


# Register functions
functions = {
    'get_user_settings': get_user_settings,
    'update_notification_preferences': update_notification_preferences,
    'update_privacy_preferences': update_privacy_preferences,
    'update_security_settings': update_security_settings,
    'update_account_preferences': update_account_preferences,
    'change_password': change_password,
    'enable_two_factor_auth': enable_two_factor_auth,
    'disable_two_factor_auth': disable_two_factor_auth,
}