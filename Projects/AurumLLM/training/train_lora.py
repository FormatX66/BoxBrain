#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_texts(path: Path) -> list[str]:
    texts: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            text = record.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
    if not texts:
        raise RuntimeError("training corpus contained no text records")
    return texts


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a reversible Aurum LoRA adapter")
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-model", default="Qwen/Qwen3.5-0.8B")
    parser.add_argument("--max-steps", type=int, default=20)
    parser.add_argument("--max-length", type=int, default=768)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    args = parser.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from torch.utils.data import Dataset
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        DataCollatorForLanguageModeling,
        Trainer,
        TrainingArguments,
    )

    if not torch.cuda.is_available():
        raise RuntimeError("Aurum adapter training requires a proven CUDA device for this lane")

    texts = load_texts(args.corpus)
    tokenizer = AutoTokenizer.from_pretrained(args.base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    class CorpusDataset(Dataset):
        def __init__(self, values: list[str]) -> None:
            self.values = values

        def __len__(self) -> int:
            return len(self.values)

        def __getitem__(self, index: int):
            encoded = tokenizer(
                self.values[index],
                truncation=True,
                max_length=args.max_length,
                add_special_tokens=True,
            )
            return {"input_ids": encoded["input_ids"], "attention_mask": encoded["attention_mask"]}

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        args.base_model,
        torch_dtype=dtype,
        trust_remote_code=True,
    )
    model.config.use_cache = False
    model.gradient_checkpointing_enable()
    model = get_peft_model(
        model,
        LoraConfig(
            r=16,
            lora_alpha=32,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules="all-linear",
        ),
    )
    model.print_trainable_parameters()

    args.output.mkdir(parents=True, exist_ok=True)
    training = TrainingArguments(
        output_dir=str(args.output / "trainer"),
        max_steps=max(1, args.max_steps),
        learning_rate=args.learning_rate,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        logging_steps=1,
        save_strategy="no",
        report_to=[],
        seed=66,
        data_seed=66,
        fp16=dtype == torch.float16,
        bf16=dtype == torch.bfloat16,
        remove_unused_columns=False,
    )
    trainer = Trainer(
        model=model,
        args=training,
        train_dataset=CorpusDataset(texts),
        data_collator=DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False),
    )
    result = trainer.train()
    adapter = args.output / "adapter"
    model.save_pretrained(adapter)
    tokenizer.save_pretrained(adapter)
    receipt = {
        "schema": "aurum-llm-training-receipt-v1",
        "generation": "adapter-0",
        "status": "trained-not-promoted",
        "base_model": args.base_model,
        "method": "lora",
        "corpus_sha256": file_sha256(args.corpus),
        "records": len(texts),
        "max_steps": args.max_steps,
        "metrics": result.metrics,
        "cuda_device": torch.cuda.get_device_name(0),
        "openai_training_data": False,
        "promotion_authorized": False,
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (args.output / "training-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
