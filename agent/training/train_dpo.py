import argparse
import torch
import os
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, TrainingArguments
from trl import DPOTrainer

def main():
    parser = argparse.ArgumentParser(description="Fine-tune a model using DPO.")
    parser.add_argument("--model_id", type=str, required=True, help="Base SFT-tuned model ID (path to LoRA adapters).")
    parser.add_argument("--dataset_path", type=str, required=True, help="Path to the DPO preference dataset in JSONL format.")
    parser.add_argument("--output_dir", type=str, required=True, help="Directory to save the final DPO-tuned LoRA adapters.")
    parser.add_argument("--epochs", type=int, default=1, help="Number of training epochs.")
    parser.add_argument("--batch_size", type=int, default=1, help="Training batch size per device.")
    parser.add_argument("--learning_rate", type=float, default=1e-5, help="Learning rate for DPO (usually lower than SFT).")
    args = parser.parse_args()

    print(f"Loading base model from SFT adapters: {args.model_id}")

    quantization_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=quantization_config,
        device_map="auto",
        trust_remote_code=True
    )
    
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = 'left'

    print(f"Loading DPO dataset from: {args.dataset_path}")
    dataset = load_dataset("json", data_files=args.dataset_path, split="train")

    training_args = TrainingArguments(
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=4,
        num_train_epochs=args.epochs,
        learning_rate=args.learning_rate,
        output_dir=args.output_dir,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        logging_steps=10,
        save_strategy="epoch",
        fp16=True, # Use fp16 for training
    )
    
    peft_config = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=[
            "q_proj",
            "o_proj",
            "k_proj",
            "v_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        bias="none",
        task_type="CAUSAL_LM",
    )

    dpo_trainer = DPOTrainer(
        model,
        ref_model=None,
        args=training_args,
        train_dataset=dataset,
        tokenizer=tokenizer,
        peft_config=peft_config,
        beta=0.1,
        max_prompt_length=512,
        max_length=1024,
    )

    print("Starting DPO training...")
    dpo_trainer.train()

    print(f"Saving DPO-tuned LoRA adapters to {args.output_dir}")
    dpo_trainer.save_model(args.output_dir)
    print("DPO Training complete!")

if __name__ == "__main__":
    main()