import json
import os
from django.core.management.base import BaseCommand
from chat.models import ChatMessage
from .export_feedback_data import Command as FeedbackCommand 

class Command(BaseCommand):
    help = 'Exports admin-corrected routing decisions into a .jsonl file for re-training the router.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output_file',
            type=str,
            help='The path to the output .jsonl file for the router.',
            default='../agent/data/agents/router_sft_data_from_feedback.jsonl'
        )

    def handle(self, *args, **options):
        output_file = options['output_file']
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        self.stdout.write(f"Exporting corrected router data to {output_file}...")

        corrected_route_messages = ChatMessage.objects.filter(
            is_reviewed=True,
            corrected_route__isnull=False
        ).exclude(corrected_route__exact='')

        feedback_exporter = FeedbackCommand()
        count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            for message in corrected_route_messages:
                prompt_context = feedback_exporter.get_prompt_for_message(message)
                
                all_agents = list(CONFIG.get('agents', {}).keys())
                
                router_prompt = f"Given the user's query, determine which of the following agents is best suited to respond. The available agents are: {all_agents}.\n\n{prompt_context}\nAgent:"
                
                completion = message.corrected_route
                
                data = {
                    "prompt": router_prompt,
                    "completion": completion
                }
                f.write(json.dumps(data) + '\n')
                count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Successfully exported {count} corrected routing examples.'))

from chat.views import CONFIG