# Plannix — Technical Documentation Source Reference

> Auto-generated exploration reference for writing comprehensive technical documentation.
> Covers every source file in `D:\AbiLabs\Plannix` except vendored third-party libs
> (`static/lib/owlcarousel`, `animate`, `easing`, `wow`, `waypoints`) and compiled
> Python caches. Full template source is reproduced verbatim; Python/config is documented per file.

---

## 1. Directory Tree

```
Plannix/
├── .claude/
├── .env                         # SECRET — gitignored, holds SECRET_KEY/email creds
├── .gitignore
├── LICENSE
├── PROJECT_WORKFLOW.md          # Hand-written source-of-truth doc
├── README.md
├── product.md                   # Product doc (ADRs, scope)
├── manage.py
├── requirements.txt
├── db.sqlite3                   # gitignored
├── Plannix/                     # Django project config package
│   ├── __init__.py
│   ├── asgi.py
│   ├── context_processors.py    # site name, user_role, notification_count
│   ├── settings.py
│   ├── urls.py                  # root routing + custom error handlers
│   └── wsgi.py
├── account_manager/             # Auth + profile app
│   ├── __init__.py
│   ├── admin.py                 # empty
│   ├── apps.py
│   ├── decorators.py            # RBAC decorators + get_role()
│   ├── migrations/__init__.py
│   ├── models.py                # empty (uses contrib.auth)
│   ├── tests.py                 # ~21 tests
│   ├── urls.py
│   └── views.py                 # sign_up/sign_in/sign_out/profile/change_password
├── events/                      # Core business app
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── management/commands/seed_demo.py
│   ├── migrations/              # 0001..0008
│   ├── models.py                # Event_Company, Event_Booking
│   ├── tests.py                 # ~48 tests
│   ├── urls.py
│   └── views.py                 # catalogue, booking, dashboards, management, errors
├── themes/                      # Public pages + Feedback app
│   ├── __init__.py
│   ├── admin.py
│   ├── apps.py
│   ├── migrations/              # 0001, 0002
│   ├── models.py                # Feedback
│   ├── templatetags/plannix_filters.py  # get_item filter
│   ├── tests.py                 # empty (no coverage)
│   ├── urls.py
│   └── views.py                 # index/about/feedback/success/error/privacy_policy
├── templates/                   # 29 HTML files (see §6)
├── static/
│   ├── css/bootstrap.min.css, style.css
│   ├── icon/                    # favicon set + webmanifest
│   ├── img/                     # logo, marks, galleries, team, testimonials
│   ├── js/main.js
│   └── lib/                     # vendored 3rd-party (owl, animate, easing, wow, waypoints)
├── media/                       # uploaded event images (gitignored)
├── event_images/                # seed source images by category (birthday/catering/corperate/dj/wedding)
├── screenshots/                 # README screenshots + demo gif
└── scripts/
    ├── capture_screenshots.py   # Playwright README screenshotter
    └── generate_assets.py       # Pillow brand-asset generator
```

---

## 2. Tech Stack & Key Facts

- **Framework:** Django 6.0.1 on Python 3.13 (supports 3.12+). Not a typo — Django 6.0.1 is what `requirements.txt` pins.
- **Database:** SQLite3 (`db.sqlite3`).
- **Auth/RBAC:** Django Groups (`admin`, `staff`, `customer`) + custom decorators in `account_manager/decorators.py`. Superuser ⇒ admin.
- **Session timeout:** `django-session-timeout` middleware (1800s idle; expires at browser close).
- **Admin:** Jazzmin branded at `/core-admin/`.
- **Email:** Console backend in dev (`EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'`).
- **Config:** `django-environ` reading `.env`.
- **UI:** Bootstrap 5.3.3 (vendored `bootstrap.min.css`) + custom design system (`static/css/style.css`).
- **Forms:** No Django ModelForms for core flows — raw `<input>` parsed manually in views. Only `PasswordChangeForm` is used.
- **JS:** No AJAX/fetch — all mutations are full-page POSTs. `main.js` does toasts, scroll-reveal, sidebar toggle, counters.
- **Data model quirk:** `Event_Booking` is **denormalized** — it copies name/type/price/location/mobile from `Event_Company` at creation (no FK). `event_booking_date` is a `CharField(max_length=10)` holding `YYYY-MM-DD`, not a `DateField` (conflict detection is string-based).

### ⚠️ Documentation inconsistencies worth flagging
1. **Demo accounts mismatch:** `product.md` §3.1 lists `plannix_admin`/`Demo@Admin123` and `plannix_staff`/`Demo@Staff123`. These **do not exist** in `seed_demo.py`. The real seed accounts are `admin` (random/printed password), `staff1`/`staffpass123`, `priya`/`arjun`/`meera`/`rahul` all on `customer123`.
2. **Nexvent legacy branding:** `.gitignore` and email (`nextventinfo@gmail.com`, EMAIL_HOST_USER in `.env`) still reference the prior "Nexvent" project. Site is now "Plannix".
3. **`error.html` vs `500.html`:** Both exist. `error.html` is reached via the `error` URL/route; `500.html` is the handler500 template. They are visually near-identical.

---

## 3. Project Config Package — `Plannix/`

### `Plannix/settings.py`
- `INSTALLED_APPS`: `jazzmin`, `django.contrib.*`, `humanize`, `themes`, `events`, `account_manager`.
- `MIDDLEWARE`: includes `django_session_timeout.middleware.SessionTimeoutMiddleware`.
- `TEMPLATES`: `DIRS=[BASE_DIR/'templates']`; context processor `Plannix.context_processors.plannix_context`.
- `DATABASES`: SQLite.
- `LOGIN_URL='sign_in'`; `TIME_ZONE='Asia/Kolkata'`.
- `MEDIA_URL='media/'`, `MEDIA_ROOT=BASE_DIR/'media'`; `STATICFILES_DIRS=[BASE_DIR/'static']`.
- Console email backend; session timeout 1800s; `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`/`SECURE_SSL_REDIRECT` = `False` (dev); HSTS 1 year, preload/subdomains off.
- `MESSAGE_TAGS` mapped to Bootstrap classes.
- `JAZZMIN_SETTINGS` + `JAZZMIN_UI_TWEAKS` (cosmo theme) for branding.

### `Plannix/urls.py`
- `path('core-admin/', admin.site.urls)`
- `include('themes.urls')`, `include('events.urls')`, `include('account_manager.urls')`
- `handler404/403/500 → events.views.error_404/403/500`
- Dev static/media serving.

### `Plannix/context_processors.py`
`plannix_context(request)` returns: `site_name='Plannix'`, `user_role` (via `get_role`), `notification_count` (pending bookings for staff/admin; non-cancelled for customers).

### `Plannix/context_processors.py`, `wsgi.py`, `asgi.py`, `__init__.py`
- `wsgi.py`/`asgi.py`: standard Django.
- `__init__.py`: empty.

---

## 4. App: `account_manager`

### `account_manager/decorators.py`
- `get_role(user)` → `'admin'` (superuser or in `admin` group), `'staff'` (in `staff` group), `'customer'` (else, including anonymous→`'anonymous'`? returns `'customer'` for any non-staff/non-admin; in practice used on authenticated users), else logic: superuser→admin, group check, default customer.
- `unauthenticated_user` — redirects logged-in users to `dashboard`.
- `allowed_roles(allowed_roles=())` — denies with `messages.error` + `redirect('dashboard')`.
- `admin_only = allowed_roles(['admin'])`
- `staff_or_admin = allowed_roles(['staff','admin'])`

### `account_manager/views.py`
- `sign_up` — validates unique username/email, password match, `create_user`, sends welcome email to `PLANNIX_SITE_URL='https://plannix.example.com'`; wrapped in `@unauthenticated_user`.
- `sign_in` — `authenticate` + `login` → `dashboard`; generic error on failure.
- `sign_out` — logout.
- `profile` — edit first/last/email (unique email, required); `@login_required(login_url='sign_in')`.
- `change_password` — `PasswordChangeForm` + `update_session_auth_hash`.

### `account_manager/urls.py`
Routes: `sign-up`, `sign-in`, `sign-out`, `profile`, `change-password`.

### `account_manager/tests.py` (~21 tests)
`SignUpTests`, `SignInTests`, `SignOutTests`, `ProfileTests`, `PasswordChangeTests`. Uses `Client(SERVER_NAME='localhost')` because `ALLOWED_HOSTS` rejects default `testserver`.

### `account_manager/models.py`, `admin.py`, `apps.py`
- `models.py`: empty (relies on `django.contrib.auth`).
- `admin.py`: empty.
- `apps.py`: `AccountManagerConfig`.

---

## 5. App: `events` (core business)

### `events/models.py`
- `Event_Company`: `event_img` (ImageField, `upload_to='events'`), `event_name`, `event_type` (CharField 30), `event_price` (BigIntegerField), `event_description` (TextField), `event_mobile_number` (10), `package1..4` (30), `mob_number` (10), `location` (30), `created_at`.
- `Event_Booking`: `user` FK→`AUTH_USER_MODEL` (null/blank, `on_delete=SET_NULL`, `related_name='bookings'`), `status` (choices pending/confirmed/completed/cancelled, default pending), `name` (30), `email` (EmailField), `number` (10), `event_company_name` (30), `event_type` (30), `event_price` (BigIntegerField), `event_booking_date` (CharField 10 = `YYYY-MM-DD`), `event_location` (30), `event_mobile_number` (10), `created_at`.

### `events/views.py`
- **Email helpers:** `send_booking_email`, `send_status_email`.
- **Public:** `events` (type filter), `readmore`, `searching_events` (Q over name/type/price/location).
- **Booking:** `selected_event` (login, booking form), `event_booking` (validates required/past date/10-digit mobile/same-date+type conflict; creates pending booking; sends email).
- **Dashboards:** `dashboard` (role router), `customer_dashboard`, `staff_dashboard` (`@staff_or_admin`), `admin_dashboard` (`@admin_only`).
- **Customer:** `my_bookings`, `cancel_booking` (own only; not if completed/cancelled).
- **Management:** `manage_events`, `_event_from_post` (shared parser; price must be digit), `add_event`, `edit_event`, `delete_event`; `manage_bookings`, `update_booking_status` (whitelist `BOOKING_STATUSES`), `delete_booking`; `manage_feedback`, `delete_feedback`; `manage_users`, `toggle_user_active`, `delete_user` (self/superuser guards).
- **Errors:** `error_404`, `error_403`, `error_500`.

### `events/urls.py`
Routes for catalogue, booking (`selected_event`, `event_booking`), dashboards, `my_bookings`, `cancel_booking`, and management: `manage_events` (+`add_event`/`edit_event`/`delete_event`), `manage_bookings` (+`update_booking_status`/`delete_booking`), `manage_feedback` (+`delete_feedback`), `manage_users` (+`toggle_user_active`/`delete_user`).

### `events/admin.py`
`Event_CompanyAdmin` (fieldsets main/packages/meta, readonly `created_at`), `Event_BookingAdmin`.

### `events/apps.py`
`EventsConfig`; `default_auto_field = BigAutoField`; `verbose_name='Plannix Events'`.

### `events/management/commands/seed_demo.py`
Idempotent seeder:
- `_roles` — creates Groups `admin`/`staff`/`customer`.
- `_users` — admin (password from `PLANNIX_ADMIN_PASSWORD` or random printed), `staff1`/`staffpass123`, customers `priya`/`arjun`/`meera`/`rahul` on `customer123`.
- `_events` — deletes legacy 5 events, then upserts 20 (Birthday/Catering/Corporate/DJ/Wedding × 4), each with one image from `event_images/<category>/`. Note: `CATEGORY_FOLDER` maps `Corporate`→`'corperate'` (matches the misspelled folder on disk).
- `_bookings` — seeds 10 only if none exist.
- `_feedback` — seeds 5 only if none exist.

### `events/tests.py` (~48 tests)
`PublicCatalogueTests`, `BookingFlowTests`, `CustomerDashboardTests`, `StaffManagementTests`, `AdminManagementTests`, `ErrorPageTests`.

### `events/migrations/`
- `0001_initial` — `Event_Company` with `event_img upload_to='media'`.
- `0002` — adds `Event_Booking` (`event_location max_length=10`).
- `0003` — adds `event_mobile_number` to `Event_Company`.
- `0004` — adds `event_mobile_number` to `Event_Booking` + widens `event_location` to 30.
- `0005` — adds `created_at` to both.
- `0006` — adds `status` + `user` FK (`SET_NULL`) + changes `event_img upload_to='events'`.
- `0007` — adds `event_img2/3/4`.
- `0008` — removes `event_img2/3/4`.

---

## 6. App: `themes` (public pages + Feedback)

### `themes/models.py`
`Feedback`: `name` (25), `email` (EmailField), `number` (10), `message` (TextField), `created_at`.

### `themes/views.py`
`index` (featured events, `type_counts`, `total_events`, `total_bookings`, `happy_customers`, `confirmed_revenue`), `about`, `feedback` (POST create + email), `success`, `error`, `privacy_policy`.

### `themes/urls.py`
Routes: `''` (index), `about`, `feedback`, `success`, `error`, `privacy-policy`.

### `themes/admin.py`
`FeedbackAdmin` (readonly `created_at`).

### `themes/templatetags/plannix_filters.py`
`get_item(dictionary, key)` filter for safe dict lookup.

### `themes/apps.py`, `tests.py`
- `apps.py`: `ThemesConfig`.
- `tests.py`: **empty (no coverage)**.

### `themes/migrations/`
`0001_initial` (Feedback), `0002_feedback_created_at`.

---

## 7. Templates (29 files) — full source

> Each template below is reproduced verbatim. Layout base templates: `base.html` (public), `dashboard_base.html` (role dashboards), `auth_base.html` (sign-in/up).

### 7.1 `templates/base.html` — public site shell
Navbar (Home/Events/About/Feedback + user dropdown or Sign In/Get Started), footer (Explore/Account/Contact), back-to-top button, message→toast queue script. Loads Inter+Sora fonts, Bootstrap Icons, `bootstrap.min.css`, `style.css`, `main.js`.

```html
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Plannix — premium event planning and management platform. Discover, book and manage your events with ease.">
  <meta name="theme-color" content="#6D5EF7">
  <title>{% block title %}Plannix — Plan It. Live It.{% endblock %}</title>

  <!-- Favicon -->
  <link rel="icon" href="{% static 'icon/favicon-32x32.png' %}" sizes="32x32" type="image/png">
  <link rel="apple-touch-icon" href="{% static 'icon/apple-touch-icon.png' %}">
  <link rel="manifest" href="{% static 'icon/site.webmanifest' %}">

  <!-- Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@600;700;800&display=swap" rel="stylesheet">

  <!-- Bootstrap Icons -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">

  <!-- Bootstrap + Plannix design system -->
  <link href="{% static 'css/bootstrap.min.css' %}" rel="stylesheet">
  <link href="{% static 'css/style.css' %}" rel="stylesheet">

  {% block extra_css %}{% endblock %}
</head>

<body class="{% block body_class %}{% endblock %}">
  <!-- Django messages → toast queue (consumed by main.js) -->
  <script>
    window.PLANNIX_MESSAGES = [
      {% for message in messages %}
      { text: "{{ message|escapejs }}", type: "{{ message.tags }}" }{% if not forloop.last %},{% endif %}
      {% endfor %}
    ];
  </script>

  <!-- ============ Navbar ============ -->
  <nav class="px-navbar navbar navbar-expand-lg" aria-label="Main navigation">
    <div class="container px-container">
      <a class="navbar-brand" href="{% url 'index' %}">
        <img src="{% static 'img/plannix-mark.svg' %}" alt="Plannix mark">
        <span>Plannix</span>
      </a>

      <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#pxNav"
              aria-controls="pxNav" aria-expanded="false" aria-label="Toggle navigation">
        <i class="bi bi-list fs-2"></i>
      </button>

      <div class="collapse navbar-collapse" id="pxNav">
        <ul class="navbar-nav mx-auto">
          <li class="nav-item">
            <a class="nav-link {% if request.resolver_match.url_name == 'index' %}active{% endif %}" href="{% url 'index' %}">Home</a>
          </li>
          <li class="nav-item">
            <a class="nav-link {% if request.resolver_match.url_name == 'events' %}active{% endif %}" href="{% url 'events' %}">Events</a>
          </li>
          <li class="nav-item">
            <a class="nav-link {% if request.resolver_match.url_name == 'about' %}active{% endif %}" href="{% url 'about' %}">About</a>
          </li>
          <li class="nav-item">
            <a class="nav-link {% if request.resolver_match.url_name == 'feedback' %}active{% endif %}" href="{% url 'feedback' %}">Feedback</a>
          </li>
        </ul>

        <div class="d-flex align-items-center gap-2">
          {% if user.is_authenticated %}
            <div class="dropdown">
              <button class="btn btn-soft d-flex align-items-center gap-2 dropdown-toggle" type="button"
                      data-bs-toggle="dropdown" aria-expanded="false">
                <span class="avatar">{{ user.first_name|default:user.username|first|upper }}</span>
                <span class="d-none d-md-inline">{{ user.first_name|default:user.username }}</span>
              </button>
              <ul class="dropdown-menu dropdown-menu-end shadow">
                <li><a class="dropdown-item" href="{% url 'dashboard' %}"><i class="bi bi-speedometer2 me-2"></i>Dashboard</a></li>
                <li><a class="dropdown-item" href="{% url 'my_bookings' %}"><i class="bi bi-ticket-perforated me-2"></i>My Bookings</a></li>
                <li><a class="dropdown-item" href="{% url 'profile' %}"><i class="bi bi-person me-2"></i>Profile</a></li>
                <li><hr class="dropdown-divider"></li>
                <li>
                  <a class="dropdown-item text-danger" href="{% url 'sign_out' %}"><i class="bi bi-box-arrow-right me-2"></i>Sign Out</a>
                </li>
              </ul>
            </div>
          {% else %}
            <a class="btn btn-ghost px-3" href="{% url 'sign_in' %}">Sign In</a>
            <a class="btn btn-brand px-3" href="{% url 'sign_up' %}">Get Started</a>
          {% endif %}
        </div>
      </div>
    </div>
  </nav>

  {% block content %}{% endblock %}

  <!-- ============ Footer ============ -->
  <footer class="px-footer">
    <div class="container px-container pt-5">
      <div class="row g-4">
        <div class="col-lg-4 col-md-6">
          <a class="footer-brand" href="{% url 'index' %}">
            <img src="{% static 'img/plannix-mark.svg' %}" alt="Plannix mark"> Plannix
          </a>
          <p class="mb-4 pe-3">A premium event planning and management platform. Discover events you love, book in seconds, and let Plannix handle the rest.</p>
          <div class="footer-social">
            <a href="#" aria-label="Facebook"><i class="bi bi-facebook"></i></a>
            <a href="#" aria-label="Twitter / X"><i class="bi bi-twitter-x"></i></a>
            <a href="#" aria-label="Instagram"><i class="bi bi-instagram"></i></a>
            <a href="#" aria-label="LinkedIn"><i class="bi bi-linkedin"></i></a>
          </div>
        </div>

        <div class="col-lg-2 col-md-6">
          <h5>Explore</h5>
          <div class="footer-links">
            <a href="{% url 'index' %}">Home</a>
            <a href="{% url 'events' %}">Events</a>
            <a href="{% url 'about' %}">About Us</a>
            <a href="{% url 'feedback' %}">Feedback</a>
          </div>
        </div>

        <div class="col-lg-3 col-md-6">
          <h5>Account</h5>
          <div class="footer-links">
            {% if user.is_authenticated %}
              <a href="{% url 'dashboard' %}">Dashboard</a>
              <a href="{% url 'my_bookings' %}">My Bookings</a>
              <a href="{% url 'profile' %}">Profile</a>
              <a href="{% url 'sign_out' %}">Sign Out</a>
            {% else %}
              <a href="{% url 'sign_in' %}">Sign In</a>
              <a href="{% url 'sign_up' %}">Create Account</a>
            {% endif %}
            <a href="{% url 'privacy_policy' %}">Privacy Policy</a>
          </div>
        </div>

        <div class="col-lg-3 col-md-6">
          <h5>Contact</h5>
          <div class="footer-links">
            <a href="mailto:hello@plannix.app"><i class="bi bi-envelope me-2"></i>hello@plannix.app</a>
            <a href="tel:+919000000000"><i class="bi bi-telephone me-2"></i>+91 90000 00000</a>
            <a href="#"><i class="bi bi-geo-alt me-2"></i>Kochi, Kerala, India</a>
          </div>
        </div>
      </div>

      <div class="footer-bottom d-flex flex-column flex-md-row justify-content-between align-items-center gap-2">
        <span>© {% now "Y" %} <a href="{% url 'index' %}">Plannix</a>. All rights reserved.</span>
        <span>Plan it. Live it.</span>
      </div>
    </div>
  </footer>

  <!-- Back to top -->
  <button class="back-to-top" type="button" aria-label="Back to top"><i class="bi bi-arrow-up"></i></button>

  <!-- Scripts -->
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  <script src="{% static 'js/main.js' %}"></script>
  {% block extra_js %}{% endblock %}
</body>
</html>
```

### 7.2 `templates/dashboard_base.html` — role dashboard shell
Sidebar nav (Dashboard, My Bookings, Browse Events; Management section for staff/admin: Events/Bookings/Feedback; System section for admin: Users + `/core-admin/`; Account: Profile/Password), topbar with notification bell + avatar, `page_title` block, `content` block. Reads `user_role` to gate nav links.

```html
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Plannix dashboard — manage your events and bookings.">
  <meta name="theme-color" content="#6D5EF7">
  <title>{% block title %}Dashboard — Plannix{% endblock %}</title>

  <link rel="icon" href="{% static 'icon/favicon-32x32.png' %}" sizes="32x32" type="image/png">
  <link rel="apple-touch-icon" href="{% static 'icon/apple-touch-icon.png' %}">

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@600;700;800&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  <link href="{% static 'css/bootstrap.min.css' %}" rel="stylesheet">
  <link href="{% static 'css/style.css' %}" rel="stylesheet">
  {% block extra_css %}{% endblock %}
</head>

<body>
  <script>
    window.PLANNIX_MESSAGES = [
      {% for message in messages %}
      { text: "{{ message|escapejs }}", type: "{{ message.tags }}" }{% if not forloop.last %},{% endif %}
      {% endfor %}
    ];
  </script>

  <div class="px-dash">
    <!-- ============ Sidebar ============ -->
    <aside class="px-sidebar" aria-label="Dashboard navigation">
      <a class="sidebar-brand" href="{% url 'dashboard' %}">
        <img src="{% static 'img/plannix-mark.svg' %}" alt="Plannix mark"> Plannix
      </a>

      <nav class="nav flex-column" style="flex:1;">
        <div class="nav-section">Main</div>
        <a class="nav-link" href="{% url 'dashboard' %}"><i class="bi bi-speedometer2"></i>Dashboard</a>
        <a class="nav-link" href="{% url 'my_bookings' %}"><i class="bi bi-ticket-perforated"></i>My Bookings</a>
        <a class="nav-link" href="{% url 'events' %}"><i class="bi bi-calendar-heart"></i>Browse Events</a>

        {% if user_role == 'staff' or user_role == 'admin' %}
          <div class="nav-section">Management</div>
          <a class="nav-link" href="{% url 'manage_events' %}"><i class="bi bi-calendar-event"></i>Events</a>
          <a class="nav-link" href="{% url 'manage_bookings' %}">
            <i class="bi bi-journal-check"></i>Bookings
            {% if notification_count %}<span class="count">{{ notification_count }}</span>{% endif %}
          </a>
          <a class="nav-link" href="{% url 'manage_feedback' %}"><i class="bi bi-chat-heart"></i>Feedback</a>
        {% endif %}

        {% if user_role == 'admin' %}
          <div class="nav-section">System</div>
          <a class="nav-link" href="{% url 'manage_users' %}"><i class="bi bi-people"></i>Users</a>
          <a class="nav-link" href="/core-admin/"><i class="bi bi-gear"></i>Admin Panel</a>
        {% endif %}

        <div class="nav-section">Account</div>
        <a class="nav-link" href="{% url 'profile' %}"><i class="bi bi-person-circle"></i>Profile</a>
        <a class="nav-link" href="{% url 'change_password' %}"><i class="bi bi-shield-lock"></i>Password</a>
      </nav>

      <div class="sidebar-footer">
        <div class="sidebar-user">
          <span class="avatar">{{ user.first_name|default:user.username|first|upper }}</span>
          <div class="min-w-0">
            <div class="uname text-truncate">{{ user.first_name|default:user.username }}</div>
            <div class="urole">{{ user_role }}</div>
          </div>
        </div>
        <a class="btn btn-ghost btn-sm w-100 mt-3" href="{% url 'sign_out' %}"
           style="background:rgba(255,255,255,.08);border-color:rgba(255,255,255,.15);color:#fff;"
           data-confirm="Sign out of Plannix?">
          <i class="bi bi-box-arrow-right me-2"></i>Sign Out
        </a>
      </div>
    </aside>

    <!-- Mobile overlay -->
    <div class="px-sidebar-overlay"></div>

    <!-- ============ Main column ============ -->
    <div class="px-main">
      <header class="px-topbar">
        <button class="btn btn-ghost btn-icon sidebar-toggle d-none" type="button" aria-label="Toggle sidebar">
          <i class="bi bi-list"></i>
        </button>
        <h1 class="page-title">{% block page_title %}Dashboard{% endblock %}</h1>
        <div class="topbar-actions">
          <a class="bell" href="{% url 'my_bookings' %}" aria-label="Notifications" title="Notifications">
            <i class="bi bi-bell"></i>
            {% if notification_count %}<span class="dot"></span>{% endif %}
          </a>
          <a class="avatar" href="{% url 'profile' %}" title="Profile">
            {{ user.first_name|default:user.username|first|upper }}
          </a>
        </div>
      </header>

      <main class="px-content">
        {% block content %}{% endblock %}
      </main>
    </div>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  <script src="{% static 'js/main.js' %}"></script>
  {% block extra_js %}{% endblock %}
</body>
</html>
```

### 7.3 `templates/auth_base.html` — sign-in/sign-up two-column shell
Left brand panel (quote, stats), right `auth-card` with `auth_header` + `auth_content` blocks.

```html
{% load static %}
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Plannix — premium event planning and management platform.">
  <meta name="theme-color" content="#6D5EF7">
  <title>{% block title %}Plannix — Account{% endblock %}</title>

  <link rel="icon" href="{% static 'icon/favicon-32x32.png' %}" sizes="32x32" type="image/png">
  <link rel="apple-touch-icon" href="{% static 'icon/apple-touch-icon.png' %}">

  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@600;700;800&display=swap" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
  <link href="{% static 'css/bootstrap.min.css' %}" rel="stylesheet">
  <link href="{% static 'css/style.css' %}" rel="stylesheet">
  {% block extra_css %}{% endblock %}
</head>

<body class="bg-white">
  <script>
    window.PLANNIX_MESSAGES = [
      {% for message in messages %}
      { text: "{{ message|escapejs }}", type: "{{ message.tags }}" }{% if not forloop.last %},{% endif %}
      {% endfor %}
    ];
  </script>

  <div class="px-auth">
    <!-- Brand panel -->
    <aside class="px-auth-panel">
      <a class="panel-brand" href="{% url 'index' %}">
        <img src="{% static 'img/plannix-mark.svg' %}" alt="Plannix mark"> Plannix
      </a>
      <div class="panel-quote">
        <p>Plan it. Live it. Remember it forever.</p>
        <span>Discover events, book in seconds, and manage everything from one beautiful dashboard.</span>
      </div>
      <div class="panel-footer d-flex gap-3" style="position:relative;z-index:1;font-size:.85rem;color:rgba(255,255,255,.6);">
        <span><i class="bi bi-calendar-check me-2"></i>10,000+ events</span>
        <span><i class="bi bi-star me-2"></i>4.9 rating</span>
      </div>
    </aside>

    <!-- Form column -->
    <main class="px-auth-form">
      <div class="auth-card">
        <div class="mb-4">
          <a href="{% url 'index' %}" class="d-inline-flex align-items-center gap-2 mb-4"
             style="font-family:var(--px-font-display);font-weight:800;font-size:1.3rem;color:var(--px-dark);">
            <img src="{% static 'img/plannix-mark.svg' %}" alt="Plannix mark" style="width:38px;height:38px;">
            Plannix
          </a>
          {% block auth_header %}{% endblock %}
        </div>

        {% block auth_content %}{% endblock %}

        <p class="text-center" style="color:var(--px-text-light);font-size:.8rem;margin-top:2.5rem;">
          &copy; {% now "Y" %} Plannix. Crafted with care.
        </p>
      </div>
    </main>
  </div>

  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
  <script src="{% static 'js/main.js' %}"></script>
  {% block extra_js %}{% endblock %}
</body>
</html>
```

### 7.4 `templates/index.html` — landing page
Extends `base.html`. Hero (search form → `searching_events`, stats with `data-counter`), About section, Event Categories grid (`event_types` + `type_counts`), 3-step process, Popular Events grid (`featured_events`), Testimonials, CTA. Uses `humanize` (intcomma) + `plannix_filters` (`get_item`).

### 7.5 `templates/events.html` — catalogue
Page hero, search form, type filter pills (`types`, `active_type`), responsive event grid with `event_img` fallback to `gallery1.jpg`, empty state.

### 7.6 `templates/readmore.html` — event detail
`event_detail` context: media, location/price/type cards, "What's included" (package1–4), price card + "Book This Event" → `selected_event`.

### 7.7 `templates/search.html` — search results
Reuses event-card grid over `events` filtered by `search_query`.

### 7.8 `templates/about.html` — about/mission/values/team
Mission copy, Values (Speed/Reliability/Creativity/Support), Team grid (team-1..4.jpg).

### 7.9 `templates/feedback.html` — public feedback form
Form → `feedback` (name/email/number/message; 10-digit pattern). Right column contact card.

### 7.10 `templates/success.html` — booking confirmation
Centered success card with "What happens next" + dashboard/events links.

### 7.11 `templates/error.html` — generic error page
Centered error card (red gradient icon) + home/events links. (Separate from `500.html`.)

### 7.12 `templates/privacy-policy.html` — legal page
9 numbered sections + effective date January 2026.

### 7.13 `templates/sign-in.html` / `templates/sign-up.html` — auth forms
Extend `auth_base.html`. Sign-in: username/password → `sign_in`. Sign-up: username/email/password/confirm (minlength 8) → `sign_up`, links to privacy policy.

### 7.14 `templates/profile.html` — edit profile
Extends `dashboard_base.html`. Left avatar card (email, joined, change-password link). Right edit form (first/last/email) → `profile`.

### 7.15 `templates/change-password.html` — password change
Uses `PasswordChangeForm` (`{{ form.*.id_for_label }}`, errors, help_text) → `change_password`.

### 7.16 `templates/event-booking-form.html` — booking form
Extends `base.html`. Left event summary (sticky). Right form → `event_booking` with hidden `event_id`/`event_mobile_number`, readonly name/email/event name, inputs for number/date (min `today_date`)/location/type/price (hidden row). No payment step.

### 7.17 `templates/event_form.html` — add/edit event
Extends `dashboard_base.html`. Shared form for `add_event`/`edit_event` (`event` context switches). Fields: name/type/price/location/vendor mobile/image/description/packages 1–4. `enctype="multipart/form-data"`.

### 7.18 `templates/customer_dashboard.html` — customer home
Stat cards (total/upcoming/spent/welcome). Upcoming bookings list (`upcoming_bookings`) + recent activity (`recent_bookings`); status badges.

### 7.19 `templates/my_bookings.html` — customer bookings table
Table of `bookings` with cancel form (`cancel_booking`, guarded by `b.status != 'cancelled'`, `data-confirm`).

### 7.20 `templates/staff_dashboard.html` — staff home
Stats (active events/total bookings/pending approval/feedback). Pending bookings queue (`recent_bookings`) + recent feedback (`recent_feedback`).

### 7.21 `templates/admin_dashboard.html` — admin home
Stats (revenue/total bookings/users/events). Booking status breakdown (`status_counts`) with progress bars + `staff_count`. Event type distribution (`type_counts`). Recent bookings + recent feedback.

### 7.22 `templates/manage_events.html` — event table
Table of `events` with edit/delete (`edit_event`/`delete_event`, `data-confirm`). "Add Event" button.

### 7.23 `templates/manage_bookings.html` — booking management
Status filter pills (`statuses`, `active_status`). Table with inline status `<select>` → `update_booking_status` + delete → `delete_booking`.

### 7.24 `templates/manage_feedback.html` — feedback table
Table `feedback_list` (name/contact/message/date) + delete → `delete_feedback`.

### 7.25 `templates/manage_users.html` — user admin
Table over `users_with_roles` (pairs of user, role). Role badge `px-role`, active/deactivated badge, toggle (`toggle_user_active`) + delete (`delete_user`, `data-confirm`).

### 7.26 Error pages `403.html` / `404.html` / `500.html`
All extend `base.html`, set `body_class px-error-body`, show large gradient error code + icon + message + action buttons. 403 redirects to dashboard (if authed) or sign-in; 404/500 to home/events.

---

## 8. Scripts (`scripts/`)

### `scripts/capture_screenshots.py`
Playwright script capturing README screenshots against dev server (127.0.0.1:8009) using system Chrome. Public shots + role shots (customer/staff/admin).

### `scripts/generate_assets.py`
Pillow generator for logo SVGs, favicon set, web manifest with brand palette `#6D5EF7`/`#9B6CF6`.

---

## 9. Static assets summary
- `css/style.css` — full design system: `:root` tokens (`--px-primary #6D5EF7`, `--px-violet #9B6CF6`, `--px-dark #0B1020`, radius/shadow/font tokens), navbar, hero, sections, event cards, status pills (`badge-pending/confirmed/completed/cancelled`, `px-role.admin/staff/customer`), alerts, footer, dashboard grid (`.px-dash` 264px 1fr, sidebar, topbar, stat, table), auth two-col, toasts, reveal animations, back-to-top, error pages, reduced-motion.
- `js/main.js` — vanilla IIFE: scroll reveal (IntersectionObserver), navbar scroll state, back-to-top, XSS-safe toast system (reads `window.PLANNIX_MESSAGES`, `escapeHtml`), animated counters (`[data-counter]`), sidebar toggle, confirm links (`[data-confirm]`), autofocus invalid, active nav. Exposes `window.Plannix`.
- `icon/` — favicon set + `site.webmanifest`. `img/` — logo, marks, galleries, team, testimonials.

---

## 10. Tests summary
- `account_manager/tests.py` (~21): sign-up/in/out, profile, password change — all via `Client(SERVER_NAME='localhost')`.
- `events/tests.py` (~48): public catalogue, booking flow (validation/conflicts), customer dashboard, staff management, admin management, error pages.
- `themes/tests.py`: **empty — zero coverage.**

---

## 11. Notable design decisions (for architecture docs)
1. **Denormalized booking** — `Event_Booking` copies vendor fields at creation; no FK to `Event_Company`. Intent: preserve booking snapshot even if the event is later edited/deleted. Trade-off: data duplication, no referential integrity.
2. **Date as `CharField`** — `event_booking_date` stored as `YYYY-MM-DD` string; conflict detection via string equality on (date + event_type). Simpler than DateField parsing but loses date arithmetic/typing.
3. **No Django Forms** — core flows use raw inputs parsed in views. Faster to write, but loses form validation/reuse.
4. **Role via Groups + decorators** — `get_role()` derives role from superuser/group membership; decorators redirect denied users to `dashboard` with a message.
5. **Idempotent seeder** — safe to run repeatedly; `_events` deletes legacy 5 then upserts 20.
6. **Message-to-toast bridge** — Django messages serialized into `window.PLANNIX_MESSAGES` in every base template, consumed by `main.js`.
