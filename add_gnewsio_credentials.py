#!/usr/bin/env python
"""
Add GNews.io credentials to CredentialStore

Run this script to add GNews.io API credentials to the database:
    python add_gnewsio_credentials.py
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mcube_ai.settings')
django.setup()

from apps.core.models import CredentialStore

# Add GNews.io credentials
gnewsio_creds, created = CredentialStore.objects.get_or_create(
    service='gnewsio',
    name='default',
    defaults={
        'api_key': 'd027318d9f16ac02e0487003402cab70',
        'username': 'avmgp.in@gmail.com',
        'password': 'Anupamvm1!',
    }
)

if created:
    print('✅ GNews.io credentials created successfully!')
    print(f'   Service: {gnewsio_creds.get_service_display()}')
    print(f'   Name: {gnewsio_creds.name}')
    print(f'   API Key: {gnewsio_creds.api_key[:8]}...')
    print(f'   Username: {gnewsio_creds.username}')
    print(f'   Created: {gnewsio_creds.created_at}')
else:
    print('ℹ️  GNews.io credentials already exist')
    print(f'   Service: {gnewsio_creds.get_service_display()}')
    print(f'   Name: {gnewsio_creds.name}')
    print(f'   API Key: {gnewsio_creds.api_key[:8]}...')
    print(f'   Username: {gnewsio_creds.username}')
    print(f'   Last Updated: {gnewsio_creds.created_at}')

    # Update if needed
    update = input('\nDo you want to update the credentials? (y/n): ').lower()
    if update == 'y':
        gnewsio_creds.api_key = 'd027318d9f16ac02e0487003402cab70'
        gnewsio_creds.username = 'avmgp.in@gmail.com'
        gnewsio_creds.password = 'Anupamvm1!'
        gnewsio_creds.save()
        print('✅ GNews.io credentials updated successfully!')

print('\n' + '='*60)
print('GNews.io Setup Complete!')
print('='*60)
print('\nYou can now use GNews.io API in your application.')
print('The API key will be retrieved from CredentialStore automatically.')
print('\nTo verify credentials, run:')
print('  python manage.py setup_credentials --status')
