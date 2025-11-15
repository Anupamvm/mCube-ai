"""
Model Management Command

This command helps download, manage, and configure LLM models.

Usage:
    python manage.py manage_models --list-recommended
    python manage.py manage_models --list-local
    python manage.py manage_models --download <repo_id> <filename>
    python manage.py manage_models --import-to-ollama <gguf_file> <model_name>
    python manage.py manage_models --quick-setup
"""

from django.core.management.base import BaseCommand
from apps.llm.services.model_manager import get_model_manager


class Command(BaseCommand):
    help = 'Manage LLM models (download, import, list)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--list-recommended',
            action='store_true',
            help='List recommended models for trading'
        )

        parser.add_argument(
            '--list-local',
            action='store_true',
            help='List locally downloaded models'
        )

        parser.add_argument(
            '--download',
            nargs=2,
            metavar=('REPO_ID', 'FILENAME'),
            help='Download model from HuggingFace (repo_id filename)'
        )

        parser.add_argument(
            '--import-to-ollama',
            nargs=2,
            metavar=('GGUF_FILE', 'MODEL_NAME'),
            help='Import GGUF model to Ollama'
        )

        parser.add_argument(
            '--delete',
            metavar='MODEL_NAME',
            help='Delete a local model'
        )

        parser.add_argument(
            '--quick-setup',
            action='store_true',
            help='Quick setup: Download and import recommended model'
        )

    def handle(self, *args, **options):
        manager = get_model_manager()

        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('LLM MODEL MANAGER'))
        self.stdout.write('=' * 80)
        self.stdout.write('')

        # List recommended models
        if options['list_recommended']:
            self.list_recommended(manager)

        # List local models
        elif options['list_local']:
            self.list_local(manager)

        # Download model
        elif options['download']:
            repo_id, filename = options['download']
            self.download_model(manager, repo_id, filename)

        # Import to Ollama
        elif options['import_to_ollama']:
            gguf_file, model_name = options['import_to_ollama']
            self.import_to_ollama(manager, gguf_file, model_name)

        # Delete model
        elif options['delete']:
            self.delete_model(manager, options['delete'])

        # Quick setup
        elif options['quick_setup']:
            self.quick_setup(manager)

        # Default: show help
        else:
            self.show_help()

    def list_recommended(self, manager):
        """List recommended models"""
        self.stdout.write(self.style.WARNING('RECOMMENDED MODELS FOR TRADING'))
        self.stdout.write('-' * 80)
        self.stdout.write('')

        recommended = manager.get_recommended_models()

        for i, model in enumerate(recommended, 1):
            self.stdout.write(f"{i}. {self.style.SUCCESS(model['name'])}")
            self.stdout.write(f"   Repo: {model['repo_id']}")
            self.stdout.write(f"   File: {model['filename']}")
            self.stdout.write(f"   Size: {model['size']}")
            self.stdout.write(f"   Description: {model['description']}")
            self.stdout.write(f"   Use Case: {model['use_case']}")
            self.stdout.write('')

            # Show download command
            self.stdout.write(f"   Download command:")
            self.stdout.write(f"   python manage.py manage_models --download {model['repo_id']} {model['filename']}")
            self.stdout.write('')

    def list_local(self, manager):
        """List local models"""
        self.stdout.write(self.style.WARNING('LOCAL MODELS'))
        self.stdout.write('-' * 80)
        self.stdout.write('')

        models = manager.list_local_models()

        if not models:
            self.stdout.write(self.style.WARNING('No local models found.'))
            self.stdout.write('')
            self.stdout.write('Download a model using:')
            self.stdout.write('  python manage.py manage_models --list-recommended')
            return

        for model in models:
            self.stdout.write(f"Name: {self.style.SUCCESS(model['name'])}")
            self.stdout.write(f"  Path: {model['file_path']}")
            self.stdout.write(f"  Size: {model['file_size_mb']} MB")
            self.stdout.write(f"  Repo: {model.get('repo_id', 'Unknown')}")
            self.stdout.write('')

        self.stdout.write(f"Total models: {len(models)}")

    def download_model(self, manager, repo_id, filename):
        """Download a model from HuggingFace"""
        self.stdout.write(self.style.WARNING(f'DOWNLOADING MODEL'))
        self.stdout.write('-' * 80)
        self.stdout.write(f"Repo: {repo_id}")
        self.stdout.write(f"File: {filename}")
        self.stdout.write('')

        self.stdout.write('Starting download...')
        self.stdout.write('This may take a while depending on model size and internet speed.')
        self.stdout.write('')

        success, result = manager.download_from_huggingface(repo_id, filename)

        if success:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'✅ Download complete!'))
            self.stdout.write(f'Model saved to: {result}')
            self.stdout.write('')
            self.stdout.write('Next steps:')
            self.stdout.write(f'  1. Import to Ollama:')
            self.stdout.write(f'     python manage.py manage_models --import-to-ollama {filename} my-model-name')
            self.stdout.write(f'  2. Or manually copy to Ollama models directory')
        else:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ Download failed: {result}'))

    def import_to_ollama(self, manager, gguf_file, model_name):
        """Import GGUF model to Ollama"""
        self.stdout.write(self.style.WARNING('IMPORTING TO OLLAMA'))
        self.stdout.write('-' * 80)
        self.stdout.write(f"GGUF File: {gguf_file}")
        self.stdout.write(f"Ollama Model Name: {model_name}")
        self.stdout.write('')

        self.stdout.write('Importing...')

        success, message = manager.import_to_ollama(gguf_file, model_name)

        if success:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS(f'✅ {message}'))
            self.stdout.write('')
            self.stdout.write('You can now use this model:')
            self.stdout.write(f'  1. Update .env: OLLAMA_MODEL={model_name}')
            self.stdout.write(f'  2. Test it: python manage.py test_llm')
        else:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ {message}'))

    def delete_model(self, manager, model_name):
        """Delete a local model"""
        self.stdout.write(self.style.WARNING(f'DELETING MODEL: {model_name}'))
        self.stdout.write('-' * 80)

        # Confirm deletion
        confirm = input(f"Are you sure you want to delete '{model_name}'? (yes/no): ")

        if confirm.lower() != 'yes':
            self.stdout.write('Deletion cancelled.')
            return

        success, message = manager.delete_model(model_name)

        if success:
            self.stdout.write(self.style.SUCCESS(f'✅ {message}'))
        else:
            self.stdout.write(self.style.ERROR(f'❌ {message}'))

    def quick_setup(self, manager):
        """Quick setup: Download and import recommended model"""
        self.stdout.write(self.style.WARNING('QUICK SETUP'))
        self.stdout.write('-' * 80)
        self.stdout.write('')

        self.stdout.write('This will download and import DeepSeek Coder 6.7B (~3.8GB)')
        self.stdout.write('This is a good balance of performance and size for trading analysis.')
        self.stdout.write('')

        confirm = input('Continue? (yes/no): ')

        if confirm.lower() != 'yes':
            self.stdout.write('Setup cancelled.')
            return

        # Download
        repo_id = "TheBloke/deepseek-coder-6.7B-instruct-GGUF"
        filename = "deepseek-coder-6.7b-instruct.Q4_K_M.gguf"
        model_name = "deepseek-coder-6.7b"

        self.stdout.write('')
        self.stdout.write('Step 1: Downloading model...')

        success, result = manager.download_from_huggingface(repo_id, filename)

        if not success:
            self.stdout.write(self.style.ERROR(f'❌ Download failed: {result}'))
            return

        self.stdout.write(self.style.SUCCESS('✅ Download complete'))

        # Import to Ollama
        self.stdout.write('')
        self.stdout.write('Step 2: Importing to Ollama...')

        success, message = manager.import_to_ollama(filename, model_name)

        if not success:
            self.stdout.write(self.style.ERROR(f'❌ Import failed: {message}'))
            self.stdout.write('')
            self.stdout.write('Model downloaded but not imported to Ollama.')
            self.stdout.write('You can manually import it later.')
            return

        self.stdout.write(self.style.SUCCESS('✅ Import complete'))

        # Success
        self.stdout.write('')
        self.stdout.write('=' * 80)
        self.stdout.write(self.style.SUCCESS('SETUP COMPLETE!'))
        self.stdout.write('=' * 80)
        self.stdout.write('')
        self.stdout.write('Next steps:')
        self.stdout.write(f'  1. Update .env file: OLLAMA_MODEL={model_name}')
        self.stdout.write('  2. Test the model: python manage.py test_llm')
        self.stdout.write('')

    def show_help(self):
        """Show usage help"""
        self.stdout.write(self.style.WARNING('USAGE'))
        self.stdout.write('-' * 80)
        self.stdout.write('')

        commands = [
            ('--list-recommended', 'List recommended models for trading'),
            ('--list-local', 'List locally downloaded models'),
            ('--download <repo> <file>', 'Download model from HuggingFace'),
            ('--import-to-ollama <gguf> <name>', 'Import GGUF to Ollama'),
            ('--delete <name>', 'Delete a local model'),
            ('--quick-setup', 'Quick setup (download + import recommended model)'),
        ]

        for cmd, desc in commands:
            self.stdout.write(f"  {self.style.SUCCESS(cmd)}")
            self.stdout.write(f"    {desc}")
            self.stdout.write('')

        self.stdout.write('Examples:')
        self.stdout.write('  python manage.py manage_models --list-recommended')
        self.stdout.write('  python manage.py manage_models --quick-setup')
        self.stdout.write('')
