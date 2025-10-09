"""
Test script for select_parser.py
Tests pluralization and relationship resolution
"""
import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ssm_backend_api.settings')
django.setup()

from ssm.select_parser import SelectParser, RelationshipResolver

def test_parser():
    print("=" * 60)
    print("TESTING SELECT PARSER")
    print("=" * 60)

    # Test 1: Basic field parsing
    print("\n[TEST 1] Basic field selection")
    query = SelectParser.parse("id,name,email")
    print(f"  Input: 'id,name,email'")
    print(f"  Fields: {[f.name for f in query.fields]}")
    print(f"  Has wildcard: {query.has_wildcard()}")

    # Test 2: Wildcard
    print("\n[TEST 2] Wildcard selection")
    query = SelectParser.parse("*")
    print(f"  Input: '*'")
    print(f"  Has wildcard: {query.has_wildcard()}")

    # Test 3: Relationship parsing
    print("\n[TEST 3] Forward relationship")
    query = SelectParser.parse("id,name,team(id,name)")
    print(f"  Input: 'id,name,team(id,name)'")
    for field in query.fields:
        if field.nested:
            print(f"  Nested field '{field.name}': {[f.name for f in field.nested.fields]}")

    # Test 4: Reverse relationship (user_set)
    print("\n[TEST 4] Reverse relationship (user_set)")
    query = SelectParser.parse("id,name,user_set(id,name,email)")
    print(f"  Input: 'id,name,user_set(id,name,email)'")
    for field in query.fields:
        if field.nested:
            print(f"  Nested field '{field.name}': {[f.name for f in field.nested.fields]}")

    # Test 5: Pluralization
    print("\n[TEST 5] Pluralization")
    test_words = ['user', 'person', 'address', 'company', 'child', 'box', 'leaf']
    print("  Testing pluralization rules:")
    for word in test_words:
        plural = RelationshipResolver._pluralize(word)
        print(f"    {word} -> {plural}")

    # Test 6: Reverse relationship with plural
    print("\n[TEST 6] Reverse relationship (plural form)")
    query = SelectParser.parse("id,name,users(id,name,email)")
    print(f"  Input: 'id,name,users(id,name,email)'")
    for field in query.fields:
        if field.nested:
            print(f"  Nested field '{field.name}': {[f.name for f in field.nested.fields]}")

    # Test 7: Model field detection (if models exist)
    print("\n[TEST 7] Model field detection")
    try:
        from ssm.models import Team as User
        print(f"  Testing with User model...")
        fields = RelationshipResolver.get_model_fields(User)
        print(f"  Total fields detected: {len(fields)}")

        # Show relationship fields
        rel_fields = {k: v for k, v in fields.items() if v['is_relation']}
        print(f"  Relationship fields: {list(rel_fields.keys())}")

        # Show reverse relationship fields
        reverse_fields = {k: v for k, v in fields.items() if v.get('is_reverse', False)}
        if reverse_fields:
            print(f"  Reverse relationship fields:")
            for name, info in reverse_fields.items():
                actual_name = info.get('actual_field_name', name)
                print(f"    '{name}' -> actual: '{actual_name}', many: {info.get('is_many', False)}")

    except ImportError as e:
        print(f"  Could not import User model: {e}")
    except Exception as e:
        print(f"  Error testing model: {e}")

    print("\n" + "=" * 60)
    print("ALL TESTS COMPLETED")
    print("=" * 60)

if __name__ == '__main__':
    test_parser()