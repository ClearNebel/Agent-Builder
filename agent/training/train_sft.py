# training/train_sft.py
import argparse
import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, TrainingArguments, EarlyStoppingCallback
from trl import SFTTrainer

def main():
    parser = argparse.ArgumentParser(description="Fine-tune a model using SFTTrainer and QLoRA.")
    parser.add_argument("--model_id", type=str, default="google/gemma-2-9b-it", help="Base model ID from Hugging Face Hub.")
    parser.add_argument("--dataset_path", type=str, required=True, help="Path to the training dataset in JSONL format.")
    parser.add_argument("--output_dir", type=str, required=True, help="Directory to save the trained LoRA adapters.")
    parser.add_argument("--epochs", type=int, default=1, help="Number of training epochs.")
    parser.add_argument("--batch_size", type=int, default=1, help="Training batch size per device.")
    parser.add_argument("--learning_rate", type=float, default=5e-5, help="Learning rate.")
    parser.add_argument("--is_chat_format", action='store_true', help="Set this flag if the dataset uses the chatml/messages format.")
    parser.add_argument("--max_seq_length", type=int, default=1024, help="Maximum sequence length for training.")
    args = parser.parse_args()

    print(f"Loading base model: {args.model_id}")

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=quantization_config,
        device_map="auto",
    )

    model = prepare_model_for_kbit_training(model)
    
    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules="all-linear",
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )
    
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    print(f"Loading dataset from: {args.dataset_path}")
    full_ds = load_dataset("json", data_files=args.dataset_path, split="train")


    splits = full_ds.train_test_split(test_size=0.1, shuffle=True, seed=42)
    train_dataset = splits["train"]
    eval_dataset  = splits["test"]

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        weight_decay=0.01,
        
        do_eval=True,
        eval_steps=100,
        save_total_limit=2,

        logging_steps=10,
        optim="paged_adamw_8bit",
        save_strategy="epoch",
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        peft_config=lora_config,
        args=training_args,
    )

    if not args.is_chat_format:
        def formatting_prompts_func(example):
            output_texts = []
            for i in range(len(example['prompt'])):
                text = f"{example['prompt'][i]}{example['completion'][i]}"
                output_texts.append(text)
            return output_texts
        
        trainer.formatting_func = formatting_prompts_func

    print("Starting training...")
    trainer.train()

    print(f"Saving LoRA adapters to {args.output_dir}")
    trainer.save_model(args.output_dir)
    print("Training complete!")

if __name__ == "__main__":
    main()