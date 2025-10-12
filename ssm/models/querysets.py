from django.db import models
from django.utils import timezone
from datetime import timedelta


class SimCardQuerySet(models.QuerySet):
    def registered_today(self):
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        return self.filter(
            registered_on__isnull=False,
            registered_on__gte=today_start,
            registered_on__lt=today_end
        )

    def registered_yesterday(self):
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        return self.filter(
            registered_on__isnull=False,
            registered_on__gte=yesterday_start,
            registered_on__lt=today_start
        )

    def quality_cards(self):
        return self.filter(quality='Y')

    def non_quality_cards(self):
        return self.filter(quality='N')

    def assigned_cards(self):
        return self.filter(assigned_to_user__isnull=False)

    def unassigned_cards(self):
        return self.filter(assigned_to_user__isnull=True)

    def active_cards(self):
        return self.filter(status='REGISTERED', fraud_flag=False)


class UserQuerySet(models.QuerySet):
    def active_users(self):
        return self.filter(status='ACTIVE', deleted=False)

    def team_members(self):
        return self.exclude(role='team_leader')

    def team_leaders(self):
        return self.filter(role='team_leader')


class TeamQuerySet(models.QuerySet):
    def active_teams(self):
        return self.filter(is_active=True)


class LotMetadataQuerySet(models.QuerySet):
    def assigned_lots(self):
        return self.filter(assigned_team__isnull=False)

    def pending_lots(self):
        return self.filter(status='PENDING')