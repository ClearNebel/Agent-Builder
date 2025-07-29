import json
import os
from django.core.management.base import BaseCommand
from chat.models import ChatMessage

from chat.views import ALL_SYSTEM_AGENTS

class Command(BaseCommand):
    help = 'Exports user feedback data into a .jsonl file for model training.'

    def add_arguments(self, parser):
        parser.add_argument(
            'agent_name',
            type=str,
            help='The name of the agent to export data for (e.g., "programmer", "teacher").'
        )
        parser.add_argument(
            '--output_file',
            type=str,
            help='(Optional) The path to the output .jsonl file. Defaults to agent/data/<agent_name>_dpo_data.jsonl'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['sft', 'dpo'],
            default='dpo', 
            help="Output format: 'sft' for fine-tuning on good examples, 'dpo' for preference pairs."
        )

    def handle(self, *args, **options):
        agent_name = options['agent_name']
        output_format = options['format']
        output_file = options['output_file']

        if agent_name not in ALL_SYSTEM_AGENTS:
            self.stderr.write(self.style.ERROR(f"Error: Agent '{agent_name}' is not defined in config.yaml."))
            return

        if not output_file:
            output_file = f'../agent/data/agents/{agent_name}_{output_format}_data.jsonl'

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        self.stdout.write(f"Exporting '{output_format}' data for agent '{agent_name}' to {output_file}...")

        if output_format == 'sft':
            self.export_sft_format(agent_name, output_file)
        elif output_format == 'dpo':
            self.export_dpo_format(agent_name, output_file)

        self.stdout.write(self.style.SUCCESS(f'Successfully exported data.'))

    def get_prompt_for_message(self, message: ChatMessage):
        """
        Reconstructs the prompt (user query + history) that led to a specific agent message.
        """
        previous_messages = message.conversation.messages.filter(
            created_at__lt=message.created_at
        ).order_by('created_at')
        
        user_query = (previous_messages[len(previous_messages) - 1]).content
        print(user_query)

        if not user_query:
            last_user_message = previous_messages.filter(role=ChatMessage.Role.USER).last()
            if last_user_message:
                user_query = last_user_message.content

        return f"{user_query}"

    def export_sft_format(self, agent_name, output_file):
        """
        Exports all 'thumbs up' responses for a SPECIFIC agent.
        """
        count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            thumbs_up_messages = ChatMessage.objects.filter(
                feedback=ChatMessage.Feedback.THUMBS_UP,
                role=ChatMessage.Role.AGENT,
                agent_name__iexact=agent_name.capitalize()
            ).select_related('conversation')

            for message in thumbs_up_messages:
                prompt_context = self.get_prompt_for_message(message)
                user_content = f"{prompt_context}"
                data = {"prompt": f"{user_content}", "completion": f"{message.content}"}
                f.write(json.dumps(data) + '\n')
                count += 1
        
        self.stdout.write(f"Exported {count} high-quality (thumbs-up) examples for agent '{agent_name}'.")


    def export_dpo_format(self, agent_name, output_file):
        """
        Creates a preference dataset for a SPECIFIC agent.
        """
        count = 0
        with open(output_file, 'w', encoding='utf-8') as f:
            rejected_and_corrected = ChatMessage.objects.filter(
                agent_name__iexact=agent_name.capitalize(),
                feedback=ChatMessage.Feedback.THUMBS_DOWN,
                is_reviewed=True,
                corrected_content__isnull=False
            )
            for rejected_msg in rejected_and_corrected:
                if not rejected_msg.corrected_content:
                    continue

                prompt = self.get_prompt_for_message(rejected_msg)
                
                data = {
                    "prompt": prompt,
                    "chosen": rejected_msg.corrected_content,
                    "rejected": rejected_msg.content
                }
                
                f.write(json.dumps(data) + '\n')
                count += 1

        self.stdout.write(f"Exported {count} preference pairs for agent '{agent_name}'.")

