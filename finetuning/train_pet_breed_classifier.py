import os
import json
import copy
import random
import warnings
import multiprocessing
from collections import Counter

from PIL import Image

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

import torch
import torch.nn as nn
import torch.optim as optim
from torch.amp import autocast, GradScaler
from torch.utils.data import Dataset, DataLoader
from torchvision import models, transforms

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix
)

warnings.filterwarnings("ignore")


# =========================================================
# 1. CONFIG
# =========================================================
IMAGES_DIR = r"E:\Ideas\images"

# Output files will be saved in the SAME folder as this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_SAVE_PATH = os.path.join(SCRIPT_DIR, "mobilenetv3_pet_best.pth")
CLASS_MAP_SAVE_PATH = os.path.join(SCRIPT_DIR, "class_names.json")
METRICS_JSON_PATH = os.path.join(SCRIPT_DIR, "final_metrics.json")

LOSS_CURVE_PATH = os.path.join(SCRIPT_DIR, "loss_curve.png")
ACCURACY_CURVE_PATH = os.path.join(SCRIPT_DIR, "accuracy_curve.png")
TOP3_CURVE_PATH = os.path.join(SCRIPT_DIR, "top3_accuracy_curve.png")
F1_CURVE_PATH = os.path.join(SCRIPT_DIR, "f1_curve.png")
CONFUSION_MATRIX_PATH = os.path.join(SCRIPT_DIR, "confusion_matrix.png")

IMG_SIZE = 224
BATCH_SIZE = 64            # Good for RTX A4500 16GB
NUM_WORKERS = 0            # IMPORTANT: Windows-safe fix
HEAD_EPOCHS = 8
FINE_TUNE_EPOCHS = 10
HEAD_LR = 1e-3
FINE_TUNE_LR = 1e-4
WEIGHT_DECAY = 1e-4

TEST_SPLIT = 0.15          # 15% test
VAL_SPLIT = 0.15           # 15% validation
SEED = 42


# =========================================================
# 2. DATASET CLASS
# =========================================================
class PetBreedDataset(Dataset):
    """
    Dataset for filenames like:
    pug_1.jpg
    pug_2.jpg
    persian_10.jpg

    Breed name is extracted as everything before the last underscore-number.
    """
    def __init__(self, samples, class_names, transform=None):
        self.samples = samples  # list of (image_path, label)
        self.class_names = class_names
        self.transform = transform

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        image_path, label = self.samples[idx]
        image = Image.open(image_path).convert("RGB")

        if self.transform:
            image = self.transform(image)

        return image, label


# =========================================================
# 3. HELPERS
# =========================================================
def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def extract_breed_from_filename(filename):
    """
    Example:
    pug_1.jpg -> pug
    british_shorthair_12.jpg -> british_shorthair
    """
    stem = os.path.splitext(filename)[0]
    parts = stem.split("_")

    # remove last numeric part if it exists
    if len(parts) >= 2 and parts[-1].isdigit():
        breed = "_".join(parts[:-1])
    else:
        # fallback if filename doesn't end in number
        breed = stem

    return breed.lower()


def collect_samples(images_dir):
    valid_exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    image_files = [
        f for f in os.listdir(images_dir)
        if os.path.isfile(os.path.join(images_dir, f)) and f.lower().endswith(valid_exts)
    ]

    if len(image_files) == 0:
        raise ValueError(f"No image files found in {images_dir}")

    breed_names = [extract_breed_from_filename(f) for f in image_files]
    class_names = sorted(list(set(breed_names)))
    class_to_idx = {cls: idx for idx, cls in enumerate(class_names)}

    samples = []
    labels = []

    for f in image_files:
        breed = extract_breed_from_filename(f)
        label = class_to_idx[breed]
        path = os.path.join(images_dir, f)
        samples.append((path, label))
        labels.append(label)

    return samples, labels, class_names, class_to_idx


def print_class_distribution(samples, class_names, title):
    counts = Counter([label for _, label in samples])
    print(f"\n{title} distribution:")
    print("-" * 50)
    for idx, cls_name in enumerate(class_names):
        print(f"{cls_name:30s} : {counts.get(idx, 0)}")


def calculate_topk_accuracy(outputs, labels, k=3):
    _, topk_preds = torch.topk(outputs, k, dim=1)
    correct = topk_preds.eq(labels.view(-1, 1).expand_as(topk_preds))
    return correct.any(dim=1).float().mean().item()


def evaluate_model(model, loader, criterion, device, use_amp):
    model.eval()
    running_loss = 0.0

    all_labels = []
    all_preds = []
    all_top3 = []

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device, non_blocking=True)
            labels = labels.to(device, non_blocking=True)

            with autocast(device_type="cuda", enabled=use_amp):
                outputs = model(images)
                loss = criterion(outputs, labels)

            running_loss += loss.item() * images.size(0)

            preds = torch.argmax(outputs, dim=1)
            all_labels.extend(labels.cpu().numpy())
            all_preds.extend(preds.cpu().numpy())

            batch_top3 = calculate_topk_accuracy(outputs, labels, k=3)
            all_top3.append(batch_top3)

    epoch_loss = running_loss / len(loader.dataset)
    acc = accuracy_score(all_labels, all_preds)
    top3_acc = float(np.mean(all_top3))

    precision, recall, f1, _ = precision_recall_fscore_support(
        all_labels, all_preds, average='weighted', zero_division=0
    )

    return {
        "loss": epoch_loss,
        "acc": acc,
        "top3_acc": top3_acc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "labels": all_labels,
        "preds": all_preds
    }


def train_one_epoch(model, loader, criterion, optimizer, scaler, device, use_amp):
    model.train()
    running_loss = 0.0

    all_labels = []
    all_preds = []
    all_top3 = []

    for images, labels in loader:
        images = images.to(device, non_blocking=True)
        labels = labels.to(device, non_blocking=True)

        optimizer.zero_grad(set_to_none=True)

        with autocast(device_type="cuda", enabled=use_amp):
            outputs = model(images)
            loss = criterion(outputs, labels)

        scaler.scale(loss).backward()
        scaler.step(optimizer)
        scaler.update()

        running_loss += loss.item() * images.size(0)

        preds = torch.argmax(outputs, dim=1)
        all_labels.extend(labels.cpu().numpy())
        all_preds.extend(preds.cpu().numpy())

        batch_top3 = calculate_topk_accuracy(outputs, labels, k=3)
        all_top3.append(batch_top3)

    epoch_loss = running_loss / len(loader.dataset)
    acc = accuracy_score(all_labels, all_preds)
    top3_acc = float(np.mean(all_top3))

    precision, recall, f1, _ = precision_recall_fscore_support(
        all_labels, all_preds, average='weighted', zero_division=0
    )

    return {
        "loss": epoch_loss,
        "acc": acc,
        "top3_acc": top3_acc,
        "precision": precision,
        "recall": recall,
        "f1": f1
    }


# =========================================================
# 4. MAIN TRAINING FUNCTION
# =========================================================
def main():
    set_seed(SEED)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = device.type == "cuda"

    print("=" * 70)
    print(f"Using device       : {device}")
    if device.type == "cuda":
        print(f"GPU name           : {torch.cuda.get_device_name(0)}")
    print(f"Images directory   : {IMAGES_DIR}")
    print(f"Outputs directory  : {SCRIPT_DIR}")
    print("=" * 70)

    # -----------------------------------------------------
    # Transforms
    # -----------------------------------------------------
    train_transform = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.15, contrast=0.15, saturation=0.15),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])

    eval_transform = transforms.Compose([
        transforms.Resize((IMG_SIZE, IMG_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406],
                             std=[0.229, 0.224, 0.225]),
    ])

    # -----------------------------------------------------
    # Load all images + create splits
    # -----------------------------------------------------
    all_samples, all_labels, class_names, class_to_idx = collect_samples(IMAGES_DIR)
    num_classes = len(class_names)

    print(f"\nTotal images found : {len(all_samples)}")
    print(f"Total breeds       : {num_classes}")
    print(f"Classes            : {class_names}")

    # Save class names for inference
    with open(CLASS_MAP_SAVE_PATH, "w") as f:
        json.dump(class_names, f, indent=2)

    # First split: train_val vs test
    train_val_samples, test_samples, train_val_labels, test_labels = train_test_split(
        all_samples,
        all_labels,
        test_size=TEST_SPLIT,
        random_state=SEED,
        stratify=all_labels
    )

    # Second split: train vs val
    relative_val_split = VAL_SPLIT / (1 - TEST_SPLIT)

    train_samples, val_samples, train_labels, val_labels = train_test_split(
        train_val_samples,
        train_val_labels,
        test_size=relative_val_split,
        random_state=SEED,
        stratify=train_val_labels
    )

    print(f"\nTrain size : {len(train_samples)}")
    print(f"Val size   : {len(val_samples)}")
    print(f"Test size  : {len(test_samples)}")

    print_class_distribution(train_samples, class_names, "TRAIN")
    print_class_distribution(val_samples, class_names, "VAL")
    print_class_distribution(test_samples, class_names, "TEST")

    # -----------------------------------------------------
    # Build datasets + dataloaders
    # -----------------------------------------------------
    train_dataset = PetBreedDataset(train_samples, class_names, transform=train_transform)
    val_dataset = PetBreedDataset(val_samples, class_names, transform=eval_transform)
    test_dataset = PetBreedDataset(test_samples, class_names, transform=eval_transform)

    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=NUM_WORKERS,
        pin_memory=(device.type == "cuda")
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=(device.type == "cuda")
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=NUM_WORKERS,
        pin_memory=(device.type == "cuda")
    )

    # -----------------------------------------------------
    # Load pretrained MobileNetV3 Small
    # -----------------------------------------------------
    weights = models.MobileNet_V3_Small_Weights.DEFAULT
    model = models.mobilenet_v3_small(weights=weights)

    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, num_classes)
    model = model.to(device)

    scaler = GradScaler("cuda", enabled=use_amp)
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

    history = {
        "train_loss": [],
        "train_acc": [],
        "train_top3": [],
        "train_precision": [],
        "train_recall": [],
        "train_f1": [],

        "val_loss": [],
        "val_acc": [],
        "val_top3": [],
        "val_precision": [],
        "val_recall": [],
        "val_f1": []
    }

    best_val_acc = 0.0
    best_model_wts = copy.deepcopy(model.state_dict())

    # -----------------------------------------------------
    # STAGE 1: Train classifier head only
    # -----------------------------------------------------
    print("\n" + "=" * 70)
    print("STAGE 1: TRAINING CLASSIFIER HEAD ONLY")
    print("=" * 70)

    for param in model.features.parameters():
        param.requires_grad = False

    for param in model.classifier.parameters():
        param.requires_grad = True

    optimizer = optim.AdamW(
        model.classifier.parameters(),
        lr=HEAD_LR,
        weight_decay=WEIGHT_DECAY
    )

    for epoch in range(HEAD_EPOCHS):
        train_metrics = train_one_epoch(model, train_loader, criterion, optimizer, scaler, device, use_amp)
        val_metrics = evaluate_model(model, val_loader, criterion, device, use_amp)

        history["train_loss"].append(train_metrics["loss"])
        history["train_acc"].append(train_metrics["acc"])
        history["train_top3"].append(train_metrics["top3_acc"])
        history["train_precision"].append(train_metrics["precision"])
        history["train_recall"].append(train_metrics["recall"])
        history["train_f1"].append(train_metrics["f1"])

        history["val_loss"].append(val_metrics["loss"])
        history["val_acc"].append(val_metrics["acc"])
        history["val_top3"].append(val_metrics["top3_acc"])
        history["val_precision"].append(val_metrics["precision"])
        history["val_recall"].append(val_metrics["recall"])
        history["val_f1"].append(val_metrics["f1"])

        print(f"\n[Head Epoch {epoch+1}/{HEAD_EPOCHS}]")
        print(f"Train | Loss: {train_metrics['loss']:.4f} | Acc: {train_metrics['acc']:.4f} | Top-3: {train_metrics['top3_acc']:.4f} | F1: {train_metrics['f1']:.4f}")
        print(f"Val   | Loss: {val_metrics['loss']:.4f} | Acc: {val_metrics['acc']:.4f} | Top-3: {val_metrics['top3_acc']:.4f} | F1: {val_metrics['f1']:.4f}")

        if val_metrics["acc"] > best_val_acc:
            best_val_acc = val_metrics["acc"]
            best_model_wts = copy.deepcopy(model.state_dict())
            torch.save({
                "model_state_dict": model.state_dict(),
                "class_names": class_names
            }, MODEL_SAVE_PATH)
            print(f"✅ Saved best model (Val Acc: {best_val_acc:.4f})")

    # -----------------------------------------------------
    # STAGE 2: Fine-tune last few feature blocks
    # -----------------------------------------------------
    print("\n" + "=" * 70)
    print("STAGE 2: FINE-TUNING LAST FEATURE BLOCKS")
    print("=" * 70)

    for param in model.features[-4:].parameters():
        param.requires_grad = True

    optimizer = optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=FINE_TUNE_LR,
        weight_decay=WEIGHT_DECAY
    )

    for epoch in range(FINE_TUNE_EPOCHS):
        train_metrics = train_one_epoch(model, train_loader, criterion, optimizer, scaler, device, use_amp)
        val_metrics = evaluate_model(model, val_loader, criterion, device, use_amp)

        history["train_loss"].append(train_metrics["loss"])
        history["train_acc"].append(train_metrics["acc"])
        history["train_top3"].append(train_metrics["top3_acc"])
        history["train_precision"].append(train_metrics["precision"])
        history["train_recall"].append(train_metrics["recall"])
        history["train_f1"].append(train_metrics["f1"])

        history["val_loss"].append(val_metrics["loss"])
        history["val_acc"].append(val_metrics["acc"])
        history["val_top3"].append(val_metrics["top3_acc"])
        history["val_precision"].append(val_metrics["precision"])
        history["val_recall"].append(val_metrics["recall"])
        history["val_f1"].append(val_metrics["f1"])

        print(f"\n[Fine-Tune Epoch {epoch+1}/{FINE_TUNE_EPOCHS}]")
        print(f"Train | Loss: {train_metrics['loss']:.4f} | Acc: {train_metrics['acc']:.4f} | Top-3: {train_metrics['top3_acc']:.4f} | F1: {train_metrics['f1']:.4f}")
        print(f"Val   | Loss: {val_metrics['loss']:.4f} | Acc: {val_metrics['acc']:.4f} | Top-3: {val_metrics['top3_acc']:.4f} | F1: {val_metrics['f1']:.4f}")

        if val_metrics["acc"] > best_val_acc:
            best_val_acc = val_metrics["acc"]
            best_model_wts = copy.deepcopy(model.state_dict())
            torch.save({
                "model_state_dict": model.state_dict(),
                "class_names": class_names
            }, MODEL_SAVE_PATH)
            print(f"✅ Saved best fine-tuned model (Val Acc: {best_val_acc:.4f})")

    print("\n" + "=" * 70)
    print(f"🏆 Best Validation Accuracy Achieved: {best_val_acc:.4f}")
    print("=" * 70)

    # -----------------------------------------------------
    # FINAL TEST EVALUATION
    # -----------------------------------------------------
    model.load_state_dict(best_model_wts)

    final_metrics = evaluate_model(model, test_loader, criterion, device, use_amp)

    print("\n" + "=" * 70)
    print("FINAL TEST METRICS")
    print("=" * 70)
    print(f"Test Loss       : {final_metrics['loss']:.4f}")
    print(f"Top-1 Accuracy  : {final_metrics['acc']:.4f}")
    print(f"Top-3 Accuracy  : {final_metrics['top3_acc']:.4f}")
    print(f"Precision       : {final_metrics['precision']:.4f}")
    print(f"Recall          : {final_metrics['recall']:.4f}")
    print(f"F1-Score        : {final_metrics['f1']:.4f}")

    print("\nClassification Report:")
    print(classification_report(
        final_metrics["labels"],
        final_metrics["preds"],
        target_names=class_names,
        zero_division=0
    ))

    # -----------------------------------------------------
    # PLOT TRAINING CURVES
    # -----------------------------------------------------
    epochs = range(1, len(history["train_loss"]) + 1)

    plt.figure(figsize=(10, 6))
    plt.plot(epochs, history["train_loss"], label="Train Loss")
    plt.plot(epochs, history["val_loss"], label="Validation Loss")
    plt.title("Loss Curve")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(LOSS_CURVE_PATH, dpi=300)
    plt.show()

    plt.figure(figsize=(10, 6))
    plt.plot(epochs, history["train_acc"], label="Train Top-1 Accuracy")
    plt.plot(epochs, history["val_acc"], label="Validation Top-1 Accuracy")
    plt.title("Top-1 Accuracy Curve")
    plt.xlabel("Epoch")
    plt.ylabel("Accuracy")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(ACCURACY_CURVE_PATH, dpi=300)
    plt.show()

    plt.figure(figsize=(10, 6))
    plt.plot(epochs, history["train_top3"], label="Train Top-3 Accuracy")
    plt.plot(epochs, history["val_top3"], label="Validation Top-3 Accuracy")
    plt.title("Top-3 Accuracy Curve")
    plt.xlabel("Epoch")
    plt.ylabel("Top-3 Accuracy")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(TOP3_CURVE_PATH, dpi=300)
    plt.show()

    plt.figure(figsize=(10, 6))
    plt.plot(epochs, history["train_f1"], label="Train F1")
    plt.plot(epochs, history["val_f1"], label="Validation F1")
    plt.title("F1 Score Curve")
    plt.xlabel("Epoch")
    plt.ylabel("F1 Score")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(F1_CURVE_PATH, dpi=300)
    plt.show()

    # -----------------------------------------------------
    # CONFUSION MATRIX
    # -----------------------------------------------------
    cm = confusion_matrix(final_metrics["labels"], final_metrics["preds"])

    plt.figure(figsize=(18, 14))
    sns.heatmap(cm, cmap="Blues", xticklabels=class_names, yticklabels=class_names)
    plt.title("Confusion Matrix - Pet Breed Classification (Test Set)")
    plt.xlabel("Predicted")
    plt.ylabel("Actual")
    plt.xticks(rotation=90)
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(CONFUSION_MATRIX_PATH, dpi=300)
    plt.show()

    # -----------------------------------------------------
    # SAVE FINAL METRICS
    # -----------------------------------------------------
    results = {
        "images_dir": IMAGES_DIR,
        "num_classes": num_classes,
        "total_images": len(all_samples),
        "train_size": len(train_samples),
        "val_size": len(val_samples),
        "test_size": len(test_samples),
        "best_val_accuracy": best_val_acc,
        "test_loss": final_metrics["loss"],
        "top1_accuracy": final_metrics["acc"],
        "top3_accuracy": final_metrics["top3_acc"],
        "precision": final_metrics["precision"],
        "recall": final_metrics["recall"],
        "f1_score": final_metrics["f1"]
    }

    with open(METRICS_JSON_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print("\n✅ SAVED FILES:")
    print(f"- Best model         : {MODEL_SAVE_PATH}")
    print(f"- Class names        : {CLASS_MAP_SAVE_PATH}")
    print(f"- Metrics JSON       : {METRICS_JSON_PATH}")
    print(f"- Loss curve         : {LOSS_CURVE_PATH}")
    print(f"- Accuracy curve     : {ACCURACY_CURVE_PATH}")
    print(f"- Top-3 curve        : {TOP3_CURVE_PATH}")
    print(f"- F1 curve           : {F1_CURVE_PATH}")
    print(f"- Confusion matrix   : {CONFUSION_MATRIX_PATH}")


# =========================================================
# 5. ENTRY POINT (WINDOWS SAFE)
# =========================================================
if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()