#!/bin/sh
set -e

cd /app

echo "setuptools>=68.0.0" > /tmp/overrides.txt
uv pip install -r requirements.txt --override /tmp/overrides.txt

python manage.py migrate

for cmd in seed_base_elements seed_standard_profile seed_viz_essentials_profile \
           seed_publication_ready_profile seed_narrative_standard_profile \
           seed_chart_types seed_example_charts; do
    python manage.py "$cmd"
done

python manage.py shell -c "
import os
from django.contrib.auth import get_user_model
from allauth.account.models import EmailAddress

User = get_user_model()
username = os.environ.get('NAVIQ_USERNAME', 'siftpipe_test')
password = os.environ['NAVIQ_PASSWORD']
email = f'{username}@example.local'

user, created = User.objects.get_or_create(username=username, defaults={'email': email})
user.email = email
user.set_password(password)
user.is_staff = True
user.save()

EmailAddress.objects.filter(user=user).delete()
EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
print(f'OK: user={user.username} created={created}')
"

exec python manage.py runserver 0.0.0.0:8001
