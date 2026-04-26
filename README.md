# WePet_V2 Project Structure

```text
WePet_django/
├── .gitignore
├── manage.py
├── requirements.txt
│
├── accounts/
│   ├── __init__.py
│   ├── admin.py
│   ├── forms.py
│   ├── models.py
│   ├── urls.py
│   ├── views.py
│   └── templates/
│       └── accounts/
│           ├── login.html
│           └── signup.html
│
├── community_app/
│   ├── __init__.py
│   ├── admin.py
│   ├── models.py
│   ├── urls.py
│   ├── views.py
│   ├── migrations/
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   └── templates/
│       └── community_app/
│           └── community.html
│
├── core/
│   ├── __init__.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── breed_classifier_service.py
│   │   ├── breed_profile_service.py
│   │   ├── citizen_task_engine.py
│   │   ├── distress_service.py
│   │   ├── location_service.py
│   │   ├── recommendation_engine.py
│   │   ├── risk_engine.py
│   │   ├── storage_service.py
│   │   └── weather_service.py
│   ├── static/
│   │   ├── css/
│   │   │   └── styles.css
│   │   └── js/
│   │       ├── breed_detect.js
│   │       ├── location.js
│   │       └── ngo_breed_detect.js
│   └── templates/
│       └── base.html
│
├── data/
│   ├── breed_profiles.json
│   ├── citizen_tasks.json
│   └── distress_reports.json
│
├── finetuning/
│   ├── class_names.json
│   ├── final_metrics.json
│   ├── test_pet_breed_classifier.py
│   └── train_pet_breed_classifier.py
│
├── ngo_app/
│   ├── __init__.py
│   ├── admin.py
│   ├── forms.py
│   ├── models.py
│   ├── urls.py
│   ├── views.py
│   ├── migrations/
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   └── templates/
│       └── ngo_app/
│           └── ngo.html
│
├── pets/
│   ├── __init__.py
│   ├── admin.py
│   ├── forms.py
│   ├── models.py
│   ├── urls.py
│   ├── views.py
│   ├── migrations/
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   └── templates/
│       └── pets/
│           └── pet_owner.html
│
└── wepet_project/
    ├── __init__.py
    ├── asgi.py
    ├── settings.py
    ├── urls.py
    └── wsgi.py
```
