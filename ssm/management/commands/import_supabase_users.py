"""
Management command to import users from Supabase with their original password hashes
"""
import json
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User as AuthUser
from django.db import transaction
from ssm.models import User
from ssm.authentication import create_user_with_supabase_password, verify_password_format


class Command(BaseCommand):
    help = 'Import users from Supabase export with their original password hashes'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            help='JSON file containing Supabase user export',
            required=True
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be imported without actually creating users'
        )
    
    def handle(self, *args, **options):
        file_path = options['file']
        dry_run = options['dry_run']
        
        try:
            with open(file_path, 'r') as f:
                users_data = json.load(f)
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'File not found: {file_path}')
            )
            return
        except json.JSONDecodeError:
            self.stdout.write(
                self.style.ERROR(f'Invalid JSON in file: {file_path}')
            )
            return
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No users will be created')
            )
        
        imported_count = 0
        skipped_count = 0
        error_count = 0
        
        for user_data in users_data:
            try:
                email = user_data.get('email')
                password_hash = user_data.get('encrypted_password')  # Supabase field
                user_metadata = user_data.get('user_metadata', {})
                
                if not email:
                    self.stdout.write(
                        self.style.WARNING(f'Skipping user without email: {user_data}')
                    )
                    skipped_count += 1
                    continue
                
                # Check if user already exists
                if AuthUser.objects.filter(email=email).exists():
                    self.stdout.write(
                        self.style.WARNING(f'User already exists: {email}')
                    )
                    skipped_count += 1
                    continue
                
                if dry_run:
                    password_format = verify_password_format(password_hash) if password_hash else 'none'
                    self.stdout.write(
                        f'Would import: {email} (password format: {password_format})'
                    )
                    imported_count += 1
                    continue
                
                # Import user with Supabase password
                with transaction.atomic():
                    if password_hash:
                        # User has existing password hash from Supabase
                        auth_user, ssm_user = create_user_with_supabase_password(
                            email=email,
                            password_hash=password_hash,
                            full_name=user_metadata.get('full_name', ''),
                            id_number=user_metadata.get('id_number', ''),
                            id_front_url=user_metadata.get('id_front_url', ''),
                            id_back_url=user_metadata.get('id_back_url', ''),
                            phone_number=user_metadata.get('phone_number', ''),
                            mobigo_number=user_metadata.get('mobigo_number', ''),
                            role=user_metadata.get('role', 'staff'),
                            status='ACTIVE',
                            is_active=True
                        )
                    else:
                        # User without password - will need to reset
                        auth_user = AuthUser.objects.create_user(
                            username=email,
                            email=email,
                            password=None  # No password set
                        )
                        auth_user.set_unusable_password()
                        auth_user.save()
                        
                        ssm_user = User.objects.create(
                            auth_user_id=auth_user.id,
                            email=email,
                            full_name=user_metadata.get('full_name', ''),
                            id_number=user_metadata.get('id_number', ''),
                            id_front_url=user_metadata.get('id_front_url', ''),
                            id_back_url=user_metadata.get('id_back_url', ''),
                            phone_number=user_metadata.get('phone_number', ''),
                            mobigo_number=user_metadata.get('mobigo_number', ''),
                            role=user_metadata.get('role', 'staff'),
                            status='ACTIVE',
                            is_active=True
                        )
                
                password_format = verify_password_format(password_hash) if password_hash else 'none'
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Imported: {email} (password format: {password_format})'
                    )
                )
                imported_count += 1
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error importing {email}: {str(e)}')
                )
                error_count += 1
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Import Summary:'))
        self.stdout.write(f'  Imported: {imported_count}')
        self.stdout.write(f'  Skipped: {skipped_count}')
        self.stdout.write(f'  Errors: {error_count}')
        
        if not dry_run and imported_count > 0:
            self.stdout.write('')
            self.stdout.write(
                self.style.WARNING(
                    'Users imported with Supabase passwords can login immediately.\n'
                    'Users without passwords need to use password reset.'
                )
            )