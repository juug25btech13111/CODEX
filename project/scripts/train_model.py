import os
import sys
import json
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
# Add root path to access Flask app and db
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
sys.path.append(root_dir)

from app import create_app
from models import Feedback

MODEL_NAME = "cardiffnlp/twitter-roberta-base-sentiment-latest"
CUSTOM_MODEL_DIR = os.path.join(root_dir, "custom_model")
STATUS_FILE = os.path.join(root_dir, "training_status.json")

def update_status(status, progress=0, message=""):
    with open(STATUS_FILE, "w") as f:
        json.dump({"status": status, "progress": progress, "message": message}, f)

def get_training_data():
    app = create_app()
    with app.app_context():
        # Fetch feedbacks that aren't purely neutral/empty
        feedbacks = Feedback.query.filter(Feedback.sentiment.in_(['Positive', 'Negative'])).all()
        
        # Label mapping for CardiffNLP model
        # 0: Negative, 1: Neutral, 2: Positive
        label_map = {'Negative': 0, 'Positive': 2}
        
        texts = []
        labels = []
        for f in feedbacks:
            if f.cleaned_text:
                texts.append(f.cleaned_text)
                labels.append(label_map[f.sentiment])
                
        return texts, labels

def main():
    update_status("Starting", 5, "Extracting data from database...")
    
    texts, labels = get_training_data()
    
    if len(texts) < 50:
        update_status("Error", 0, "Insufficient data for training. Need at least 50 positive/negative feedback entries.")
        return
        
    update_status("Processing", 20, f"Preparing dataset of {len(texts)} entries...")
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    
    # Create HuggingFace dataset
    dataset_dict = {
        "text": texts,
        "label": labels
    }
    raw_dataset = Dataset.from_dict(dataset_dict)
    
    def tokenize_function(examples):
        return tokenizer(examples["text"], padding="max_length", truncation=True, max_length=128)
        
    tokenized_dataset = raw_dataset.map(tokenize_function, batched=True)
    
    # Split into train/eval
    split_dataset = tokenized_dataset.train_test_split(test_size=0.1)
    train_dataset = split_dataset["train"]
    eval_dataset = split_dataset["test"]
    
    update_status("Training", 40, "Downloading weights and initializing neural network...")
    
    # We use num_labels=3 because the base model expects 3
    model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME, num_labels=3)
    
    training_args = TrainingArguments(
        output_dir="./trainer_logs",
        learning_rate=2e-5,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        num_train_epochs=2,
        weight_decay=0.01,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
    )
    
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
    )
    
    update_status("Training", 60, "Fine-tuning model weights... This may take a few minutes.")
    trainer.train()
    
    update_status("Saving", 90, "Saving local custom model...")
    # Clean up old directory if exists
    if not os.path.exists(CUSTOM_MODEL_DIR):
        os.makedirs(CUSTOM_MODEL_DIR)
        
    model.save_pretrained(CUSTOM_MODEL_DIR)
    tokenizer.save_pretrained(CUSTOM_MODEL_DIR)
    
    update_status("Completed", 100, "Successfully trained and exported custom AI model. Application is now using the enhanced AI.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        update_status("Error", 0, str(e))
