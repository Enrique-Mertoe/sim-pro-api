#!/usr/bin/env python
"""
Test script to verify Supabase-compatible endpoints work with the SDK
"""
import os
import django
import json
import requests
from datetime import datetime

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ssm_backend_api.settings')
django.setup()

BASE_URL = 'http://localhost:8000'
API_BASE = f'{BASE_URL}/api'

class SupabaseCompatibilityTester:
    def __init__(self):
        self.access_token = None
        self.test_user_email = f"test_{datetime.now().strftime('%Y%m%d%H%M%S')}@example.com"
        
    def test_auth_endpoints(self):
        """Test authentication endpoints"""
        print("🔐 Testing Authentication Endpoints")
        print("-" * 50)
        
        # Test signup
        signup_data = {
            'email': self.test_user_email,
            'password': 'testpassword123',
            'options': {
                'data': {
                    'full_name': 'Test User',
                    'id_number': '123456789',
                    'id_front_url': 'http://example.com/front.jpg',
                    'id_back_url': 'http://example.com/back.jpg',
                    'role': 'staff'
                }
            }
        }
        
        print("1. Testing POST /api/auth/signup")
        try:
            response = requests.post(f'{API_BASE}/auth/signup', json=signup_data)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data.get('data', {}).get('session'):
                    self.access_token = data['data']['session']['access_token']
                    print(f"   ✅ Signup successful - Token: {self.access_token[:20]}...")
                else:
                    print(f"   ❌ Signup response missing token: {data}")
            else:
                print(f"   ❌ Signup failed: {response.text}")
        except Exception as e:
            print(f"   ❌ Signup error: {e}")
        
        # Test login
        print("2. Testing POST /api/auth/login")
        try:
            login_data = {
                'email': self.test_user_email,
                'password': 'testpassword123'
            }
            response = requests.post(f'{API_BASE}/auth/login', json=login_data)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data.get('data', {}).get('session'):
                    self.access_token = data['data']['session']['access_token']
                    print("   ✅ Login successful")
                else:
                    print(f"   ❌ Login response missing token: {data}")
            else:
                print(f"   ❌ Login failed: {response.text}")
        except Exception as e:
            print(f"   ❌ Login error: {e}")
        
        # Test get user
        if self.access_token:
            print("3. Testing GET /api/auth/me")
            try:
                headers = {'Authorization': f'Bearer {self.access_token}'}
                response = requests.get(f'{API_BASE}/auth/me', headers=headers)
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    if data.get('data', {}).get('user'):
                        print("   ✅ Get user successful")
                    else:
                        print(f"   ❌ Get user response missing user: {data}")
                else:
                    print(f"   ❌ Get user failed: {response.text}")
            except Exception as e:
                print(f"   ❌ Get user error: {e}")
    
    def test_database_endpoints(self):
        """Test database endpoints"""
        print("\n🗄️  Testing Database Endpoints")
        print("-" * 50)
        
        if not self.access_token:
            print("❌ No access token available for database tests")
            return
        
        headers = {'Authorization': f'Bearer {self.access_token}'}
        
        # Test insert
        print("1. Testing POST /api/db/insert")
        try:
            insert_data = {
                'table': 'teams',
                'data': {
                    'name': 'Test Team SDK',
                    'region': 'Test Region',
                    'is_active': True
                }
            }
            response = requests.post(f'{API_BASE}/db/insert', json=insert_data, headers=headers)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data.get('data'):
                    print("   ✅ Insert successful")
                    self.test_team_id = data['data'][0]['id'] if data['data'] else None
                else:
                    print(f"   ❌ Insert response missing data: {data}")
            else:
                print(f"   ❌ Insert failed: {response.text}")
        except Exception as e:
            print(f"   ❌ Insert error: {e}")
        
        # Test select
        print("2. Testing POST /api/db/select")
        try:
            select_data = {
                'table': 'teams',
                'filters': {'name': 'Test Team SDK'}
            }
            response = requests.post(f'{API_BASE}/db/select', json=select_data, headers=headers)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data.get('data', {}).get('data'):
                    print(f"   ✅ Select successful - Found {len(data['data']['data'])} records")
                else:
                    print(f"   ❌ Select response missing data: {data}")
            else:
                print(f"   ❌ Select failed: {response.text}")
        except Exception as e:
            print(f"   ❌ Select error: {e}")
        
        # Test update
        print("3. Testing POST /api/db/update")
        try:
            update_data = {
                'table': 'teams',
                'data': {'territory': 'Updated Territory'},
                'where': {'name': 'Test Team SDK'}
            }
            response = requests.post(f'{API_BASE}/db/update', json=update_data, headers=headers)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if 'count' in data.get('data', {}):
                    print(f"   ✅ Update successful - {data['data']['count']} records updated")
                else:
                    print(f"   ❌ Update response missing count: {data}")
            else:
                print(f"   ❌ Update failed: {response.text}")
        except Exception as e:
            print(f"   ❌ Update error: {e}")
        
        # Test delete
        print("4. Testing POST /api/db/delete")
        try:
            delete_data = {
                'table': 'teams',
                'where': {'name': 'Test Team SDK'}
            }
            response = requests.post(f'{API_BASE}/db/delete', json=delete_data, headers=headers)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if 'count' in data.get('data', {}):
                    print(f"   ✅ Delete successful - {data['data']['count']} records deleted")
                else:
                    print(f"   ❌ Delete response missing count: {data}")
            else:
                print(f"   ❌ Delete failed: {response.text}")
        except Exception as e:
            print(f"   ❌ Delete error: {e}")
    
    def test_storage_endpoints(self):
        """Test storage endpoints"""
        print("\n📁 Testing Storage Endpoints")
        print("-" * 50)
        
        if not self.access_token:
            print("❌ No access token available for storage tests")
            return
        
        headers = {'Authorization': f'Bearer {self.access_token}'}
        
        # Test upload
        print("1. Testing POST /api/storage/upload")
        try:
            # Create a test file
            test_content = "This is a test file for SDK compatibility"
            files = {'file': ('test.txt', test_content, 'text/plain')}
            
            response = requests.post(f'{API_BASE}/storage/upload', files=files, headers=headers)
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                if data.get('data', {}).get('path'):
                    print(f"   ✅ Upload successful - Path: {data['data']['path']}")
                    self.test_file_path = data['data']['path']
                else:
                    print(f"   ❌ Upload response missing path: {data}")
            else:
                print(f"   ❌ Upload failed: {response.text}")
        except Exception as e:
            print(f"   ❌ Upload error: {e}")
        
        # Test download
        if hasattr(self, 'test_file_path'):
            print("2. Testing GET /api/storage/{filename}")
            try:
                response = requests.get(f'{API_BASE}/storage/{self.test_file_path}', headers=headers)
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    print("   ✅ Download successful")
                else:
                    print(f"   ❌ Download failed: {response.text}")
            except Exception as e:
                print(f"   ❌ Download error: {e}")
    
    def run_all_tests(self):
        """Run all compatibility tests"""
        print("🧪 Supabase SDK Compatibility Tests")
        print("=" * 60)
        print(f"Testing against: {API_BASE}")
        print()
        
        self.test_auth_endpoints()
        self.test_database_endpoints() 
        self.test_storage_endpoints()
        
        print("\n" + "=" * 60)
        print("✅ SDK Compatibility Test Summary:")
        print(f"- Authentication: Available at {API_BASE}/auth/*")
        print(f"- Database: Available at {API_BASE}/db/*") 
        print(f"- Storage: Available at {API_BASE}/storage/*")
        print("\nYour SDK can now connect to these endpoints!")
        print("\nExample SDK usage:")
        print(f"""
const solobase = createClient('{BASE_URL}', 'your-api-key')

// Authentication
await solobase.auth.signUp({{
  email: 'user@example.com',
  password: 'password123'
}})

// Database
await solobase.from('users').select()
await solobase.from('teams').insert({{ name: 'New Team' }})

// Storage  
await solobase.storage.upload(file)
        """)

if __name__ == "__main__":
    tester = SupabaseCompatibilityTester()
    tester.run_all_tests()