# WePet 

WePet is a Django-based climate care platform for pets, community volunteers, and animal welfare NGOs. It combines live weather data, breed-specific heat risk scoring, image-based breed detection, community rescue workflows, and shelter monitoring into one MVP.

The project is organized as a standard Django app with separate modules for authentication, pet-owner tools, community actions, NGO operations, shared services, and model fine-tuning assets.

## What It Does

- Pet owners can create pet profiles, detect supported breeds from uploaded images, fetch weather for a city or GPS location, and receive climate-risk guidance.
- The risk engine estimates heat stress, dehydration, respiratory risk, surface burn risk, indoor heat risk, safe walk windows, exposure limits, hidden risk drivers, recommendations, and emergency warning signs.
- Community users can fetch climate-aware tasks, verify task completion through geotagged proof photos, earn points, build streaks, and claim simulated rewards.
- Community users can submit animal distress alerts with symptoms, location, optional photo metadata, and weather severity.
- NGOs can manage shelter profiles, register animal groups by breed and zone, monitor group-level risk using shelter weather, and update community distress tickets.
- The image classifier uses a MobileNetV3 Small model trained on 37 pet breeds and supports top-3 predictions with an unknown-breed threshold.

## Tech Stack

- Python 3.x
- Django 4.2
- MySQL
- PyTorch, TorchVision, Pillow
- Open-Meteo geocoding and weather APIs
- OpenStreetMap/Nominatim and Overpass API for nearby shelter lookup
- WhiteNoise for static-file serving in production

## Project Structure

```text
.
|-- accounts/          # Login, signup, logout using Django auth
|-- pets/              # Pet profiles, breed detection endpoint, risk analysis
|-- community_app/     # Community tasks, distress reports, rewards
|-- ngo_app/           # Shelter registry, animal groups, ticket handling
|-- core/
|   |-- services/      # Weather, risk, recommendation, storage, OSM, ML services
|   |-- static/        # Shared CSS and JavaScript
|   `-- templates/     # Base layout
|-- data/              # JSON-backed MVP data files
|-- finetuning/        # Breed classifier scripts, class map, metrics, local model
|-- media/             # Runtime uploads
|-- wepet_project/     # Django settings and root URLs
|-- manage.py
`-- requirements.txt
```

## Main Routes

| Route | Purpose |
| --- | --- |
| `/` | Redirects to `/pets/` |
| `/accounts/login/` | Login and signup page |
| `/accounts/logout/` | Logout |
| `/pets/` | Pet owner dashboard |
| `/pets/analyze/` | Run pet climate-risk analysis |
| `/pets/detect-breed/` | AJAX breed detection for pet owners |
| `/community/` | Community task and distress dashboard |
| `/community/rewards/` | Simulated rewards page |
| `/ngo/` | NGO shelter dashboard |
| `/ngo/detect-breed/` | AJAX breed detection for NGOs |
| `/admin/` | Django admin |

## Prerequisites

- Python 3.10+ recommended
- MySQL server running locally or reachable remotely
- A MySQL database named `wepet`, or custom database settings through environment variables
- The local breed model artifact at `finetuning/mobilenetv3_pet_best.pth`

The `.pth` model file is ignored by Git through `*.pth`. Keep it outside source control and provide it separately when moving the project to another machine or server.

## Setup

Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If pip cannot resolve the CUDA-tagged PyTorch packages from `requirements.txt`, install PyTorch using the official wheel index for your machine, then rerun the requirements install as needed. For CUDA 12.1 builds:

```powershell
pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
```

Create the MySQL database:

```sql
CREATE DATABASE wepet CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Set environment variables if your local database credentials differ from the defaults:

```powershell
$env:DB_NAME="wepet"
$env:DB_USER="root"
$env:DB_PASSWORD="root"
$env:DB_HOST="localhost"
$env:DB_PORT="3306"
$env:DJANGO_DEBUG="True"
$env:DJANGO_SECRET_KEY="replace-this-for-production"
```

Run migrations:

```powershell
python manage.py migrate
```

Create an admin user:

```powershell
python manage.py createsuperuser
```

Start the development server:

```powershell
python manage.py runserver
```

Open:

```text
http://127.0.0.1:8000/
```

## Configuration

The most important settings are environment-driven in `wepet_project/settings.py`.

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Development fallback key | Set a secure value in production |
| `DJANGO_DEBUG` | `True` | Use `False` in production |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost,.onrender.com` | Comma-separated host list |
| `DB_NAME` | `wepet` | MySQL database name |
| `DB_USER` | `root` | MySQL user |
| `DB_PASSWORD` | `root` | MySQL password |
| `DB_HOST` | `localhost` | MySQL host |
| `DB_PORT` | `3306` | MySQL port |

Runtime directories are created automatically by settings:

- `data/`
- `finetuning/`
- `media/`
- `media/distress_uploads/`

## Data and Persistence

Most relational data is stored in MySQL through Django models:

- Saved pet profiles
- Risk history
- Shelter profiles
- NGO animal groups
- Community task completions
- Simulated reward claims

Some MVP data remains JSON-backed:

- `data/breed_profiles.json`
- `data/citizen_tasks.json`
- `data/distress_reports.json`

This makes the distress workflow easy to inspect and portable during prototyping, but for production it should eventually move into database models.

## Breed Classifier

The classifier service loads `finetuning/mobilenetv3_pet_best.pth` lazily when a breed detection endpoint is used. It uses:

- MobileNetV3 Small
- 224x224 RGB image input
- Top-3 predictions
- Unknown threshold of `0.35`
- CPU or CUDA depending on local PyTorch availability

The current metrics in `finetuning/final_metrics.json` are:

| Metric | Value |
| --- | ---: |
| Classes | 37 |
| Total images | 7,390 |
| Best validation accuracy | 84.49% |
| Test top-1 accuracy | 85.39% |
| Test top-3 accuracy | 95.57% |
| Weighted precision | 85.62% |
| Weighted recall | 85.39% |
| Weighted F1 | 85.34% |

To train a new model, update `IMAGES_DIR` in `finetuning/train_pet_breed_classifier.py`, then run:

```powershell
python finetuning\train_pet_breed_classifier.py
```

The training script writes the model, class map, metrics, and training plots into `finetuning/`.

## External Services

WePet calls public APIs at runtime:

- Open-Meteo Geocoding API for city lookup
- Open-Meteo Forecast API for current and hourly weather
- Nominatim as a fallback city geocoder in the OSM service
- Overpass API for animal shelter and veterinary clinic lookup

No API keys are required for the current MVP services. Network failures are surfaced as user-facing error messages in the relevant workflows.

## Development Notes

Useful checks:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
```

Static files are served locally from Django. In production, `DJANGO_DEBUG=False` enables WhiteNoise compressed manifest storage, so run:

```powershell
python manage.py collectstatic
```

## Production Notes

- Set `DJANGO_DEBUG=False`.
- Use a strong `DJANGO_SECRET_KEY`.
- Configure `ALLOWED_HOSTS` for the deployed domain.
- Use managed MySQL or update the database settings for your production database.
- Ensure `finetuning/mobilenetv3_pet_best.pth` is present on the server.
- Persist `media/` and `data/` if the deployment platform has ephemeral storage.
- Run `python manage.py collectstatic` before serving production traffic.

## Current Limitations

- Distress reports use JSON storage instead of relational database tables.
- Reward claims are simulated and do not integrate with Amazon or payments.
- Uploaded proof image names are tracked, but the current distress-ticket service stores metadata rather than a full media-management workflow.
- The classifier can identify 37 trained breeds, but only some detected breeds are mapped into the climate-risk profile system.
- Public map APIs can rate-limit or time out, so nearby shelter lookup may occasionally return an availability error.

## License

No license file is currently included. Add one before publishing or distributing the project.
