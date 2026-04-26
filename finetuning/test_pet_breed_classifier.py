import os
from PIL import Image
import matplotlib.pyplot as plt

import torch
import torch.nn as nn
from torchvision import models, transforms

# =========================================================
# 1. CONFIG
# =========================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(SCRIPT_DIR, "mobilenetv3_pet_best.pth")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IMG_SIZE = 224

# =========================================================
# 2. LOAD MODEL
# =========================================================
def load_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")

    checkpoint = torch.load(MODEL_PATH, map_location=DEVICE)
    class_names = checkpoint["class_names"]
    num_classes = len(class_names)

    # Use weights=None because we are loading OUR trained weights
    model = models.mobilenet_v3_small(weights=None)

    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, num_classes)

    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(DEVICE)
    model.eval()

    print(f"✅ Model loaded successfully on {DEVICE}")
    print(f"✅ Detected {num_classes} classes")

    return model, class_names

# =========================================================
# 3. TRANSFORM
# =========================================================
predict_transform = transforms.Compose([
    transforms.Resize((IMG_SIZE, IMG_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406],
                         std=[0.229, 0.224, 0.225]),
])

# =========================================================
# 4. PREDICT FUNCTION
# =========================================================
def predict_image(model, class_names, image_path, show_image=True):
    if not os.path.exists(image_path):
        print(f"❌ File not found: {image_path}")
        return

    image = Image.open(image_path).convert("RGB")
    input_tensor = predict_transform(image).unsqueeze(0).to(DEVICE)

    with torch.no_grad():
        outputs = model(input_tensor)
        probs = torch.softmax(outputs, dim=1)
        top3_probs, top3_indices = torch.topk(probs, 3, dim=1)

    top3_probs = top3_probs[0].cpu().numpy()
    top3_indices = top3_indices[0].cpu().numpy()

    if show_image:
        plt.figure(figsize=(5, 5))
        plt.imshow(image)
        plt.axis("off")
        plt.title("Input Image")
        plt.show()

    print("\n🔍 Top-3 Predictions:")
    for rank, (idx, prob) in enumerate(zip(top3_indices, top3_probs), start=1):
        breed = class_names[idx]
        print(f"{rank}. {breed}  |  Confidence: {prob:.4f}")

    UNKNOWN_THRESHOLD = 0.35

    best_idx = top3_indices[0]
    best_prob = top3_probs[0]
    best_breed = class_names[best_idx]

    if best_prob < UNKNOWN_THRESHOLD:
        print("\n⚠️ This image is likely NOT one of the 37 trained breeds.")
        print("⚠️ It may be:")
        print("- a breed outside the trained classes")
        print("- a mixed breed")
        print("- a difficult angle / poor lighting image")
        print(f"\n❌ Final Result: UNKNOWN / UNSUPPORTED BREED")
        print(f"Closest known breed match: {best_breed}")
        print(f"Confidence: {best_prob:.4f}")
    else:
        print(f"\n✅ Final Predicted Breed: {best_breed}")
        print(f"✅ Confidence: {best_prob:.4f}")

# =========================================================
# 5. MAIN
# =========================================================
def main():
    model, class_names = load_model()

    # Replace with ANY image path you want:
    # - Can be from dataset
    # - Can be your own downloaded image
    # - Can be your own phone photo
    custom_image_path = r"E:/Ideas/WePet/finetuning/cat_beng.jpg"

    predict_image(model, class_names, custom_image_path, show_image=True)

# =========================================================
# 6. ENTRY POINT
# =========================================================
if __name__ == "__main__":
    main()