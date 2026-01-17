#!/usr/bin/env python
"""Verify GNews.io credentials"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.core.models import CredentialStore

print('\n' + '='*60)
print('All CredentialStore Entries')
print('='*60 + '\n')

creds = CredentialStore.objects.all().order_by('service')
for cred in creds:
    print(f"Service: {cred.get_service_display()}")
    print(f"  Name: {cred.name}")
    if cred.api_key:
        print(f"  API Key: {cred.api_key[:8]}...")
    if cred.username:
        print(f"  Username: {cred.username}")
    print(f"  Created: {cred.created_at}")
    print()

print(f'Total credentials: {creds.count()}')
