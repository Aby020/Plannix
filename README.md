# ⚙️ Nexvent

<div align="center">

### Professional Event Management & Booking Platform

A modern full-stack Django web application that streamlines event discovery, theme selection, online booking, and event management through secure authentication, role-based dashboards, and an intuitive user experience.

![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.x-092E20?logo=django)
![Bootstrap](https://img.shields.io/badge/Bootstrap-5-7952B3?logo=bootstrap)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite)
![License](https://img.shields.io/badge/License-MIT-yellow)

</div>

<p align="center">
  <img src="screenshots/home.png" alt="Nexvent Home Page" width="100%">
</p>

## 📖 Project Overview

Nexvent is a full-stack Django web application designed to simplify the planning, booking, and management of events through a centralized, user-friendly platform.

The platform enables users to browse event packages, explore themes, book events online, and communicate with organizers while providing administrators and staff with powerful tools for managing bookings, customers, event packages, themes, and platform operations.

Built with Django and Bootstrap, Nexvent focuses on usability, security, and maintainability while demonstrating practical implementation of authentication, CRUD operations, email notifications, role-based access control, and responsive web design.

Whether organizing weddings, corporate events, birthday celebrations, or private functions, Nexvent provides a streamlined digital solution for customers, staff members, and administrators.

## ✨ Key Features

### 👤 Authentication & User Management

- Secure user registration and login
- Role-based access control (Admin, Staff, Customer)
- Password reset functionality
- Session management
- Email verification and authentication support

### 🎉 Event Management

- Browse event packages
- Explore event themes
- Online event booking
- Event package filtering
- Detailed package information
- Booking confirmation workflow

### 🎨 Theme Management

- Wedding themes
- Birthday themes
- Corporate event themes
- Decoration packages
- Theme gallery
- Theme customization support

### 📊 Admin & Staff Dashboard

- Centralized administration panel
- Staff dashboard for operational management
- Manage event packages
- Manage themes
- Customer booking management
- Feedback management
- User management

### 📧 Communication & Notifications

- Email confirmation
- Customer feedback system
- Contact support
- Booking status communication

### 🔒 Security Features

- Django Authentication
- Secure session management
- Role-based authorization
- Protected admin panel
- Environment variable configuration

### 🎨 User Experience

- Modern responsive interface
- Mobile-friendly design
- Bootstrap 5 components
- Simple navigation
- Clean booking workflow

## 📸 Screenshots

### 🏠 Home Page

The landing page introduces Nexvent with featured event packages, popular themes, and an intuitive navigation experience for users.

<p align="center">
  <img src="screenshots/home.png" width="100%" alt="Home Page">
</p>

---

### 🎉 Event Packages

Browse a wide range of event packages including weddings, birthday celebrations, corporate events, catering, photography, and more.

<p align="center">
  <img src="screenshots/events.png" width="100%" alt="Event Packages">
</p>

---

### 🔍 Filtered Event Packages

Users can quickly filter event packages based on categories and themes to find the perfect event solution.

<p align="center">
  <img src="screenshots/filtered-events.png" width="100%" alt="Filtered Event Packages">
</p>

---

### 💬 Feedback System

Customers can submit feedback and suggestions to improve the platform and overall event experience.

<p align="center">
  <img src="screenshots/feedback.png" width="100%" alt="Feedback">
</p>

---

### 👤 User Registration

New users can create an account securely through a clean registration interface with authentication support.

<p align="center">
  <img src="screenshots/signup.png" width="100%" alt="User Registration">
</p>

---

### 🛡️ Django Administration Panel

Administrators can efficiently manage users, event packages, themes, bookings, and platform data through a customized Django admin interface.

<p align="center">
  <img src="screenshots/admin-dashboard.png" width="100%" alt="Admin Dashboard">
</p>

---

### 👨‍💼 Staff Dashboard

Staff members can manage event packages, customer bookings, and daily platform operations through a dedicated dashboard.

<p align="center">
  <img src="screenshots/staff-dashboard.png" width="100%" alt="Staff Dashboard">
</p>

## 🛠️ Technology Stack

| Category | Technologies |
|-----------|--------------|
| **Backend** | Python, Django 5.x |
| **Frontend** | HTML5, CSS3, Bootstrap 5, JavaScript |
| **Database** | SQLite3 |
| **Authentication** | Django Authentication |
| **Email Services** | SMTP (Gmail) |
| **Development Tools** | VS Code, Git, GitHub |
| **Libraries** | Pillow, Django Browser Reload, Jazzmin |
| **Deployment Ready** | Python Virtual Environment, Environment Variables (.env) |

## 📂 Project Structure

```text
Nexvent/
│
├── Nexvent/                 # Django project configuration
├── account_manager/         # Authentication & user management
├── events/                  # Event booking & management
├── themes/                  # Theme & website pages
├── templates/               # HTML templates
├── static/                  # CSS, JavaScript & assets
├── media/                   # Uploaded event images
├── screenshots/             # README screenshots
│
├── manage.py
├── requirements.txt
├── README.md
└── .env
```

## 🏗️ System Architecture

```text
                    Client Browser
                          │
                          ▼
                 Bootstrap 5 Interface
                          │
                          ▼
                  Django URL Routing
                          │
                          ▼
                 Django Views & Logic
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
 Authentication     Event Management    Theme Module
          │               │               │
          └───────────────┼───────────────┘
                          ▼
                    SQLite Database
                          │
                          ▼
                  Email Notifications
```

## ⚙️ Installation & Setup

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/Aby020/Nexvent.git
cd Nexvent
```

---

### 2️⃣ Create a Virtual Environment

#### Windows

```bash
python -m venv .venv
.venv\Scripts\activate
```

#### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 4️⃣ Configure Environment Variables

Create a `.env` file in the project root.

Example:

```env
SECRET_KEY=your_secret_key
DEBUG=True

EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
SERVER_EMAIL=your_email@gmail.com
```

---

### 5️⃣ Apply Database Migrations

```bash
python manage.py migrate
```

---

### 6️⃣ Create an Administrator Account

```bash
python manage.py createsuperuser
```

---

### 7️⃣ Run the Development Server

```bash
python manage.py runserver
```

Open your browser and visit:

```
http://127.0.0.1:8000/
```

Django Administration Panel:

```
http://127.0.0.1:8000/admin/
```

## 📦 Core Dependencies

- Django 5.x
- Django Browser Reload
- Jazzmin
- Pillow
- SQLite3
- Python-dotenv / Django Environ

## 🔐 Environment Variables

The application uses a `.env` file to securely manage configuration values.

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Django secret key |
| `DEBUG` | Enable or disable debug mode |
| `EMAIL_HOST` | SMTP server address |
| `EMAIL_PORT` | SMTP server port |
| `EMAIL_USE_TLS` | Enable TLS |
| `EMAIL_HOST_USER` | SMTP email account |
| `EMAIL_HOST_PASSWORD` | SMTP app password |
| `SERVER_EMAIL` | Sender email address |

## 📦 Project Modules

### 👤 Account Manager

Responsible for user authentication and account management.

**Features**
- User Registration
- User Login
- Password Reset
- Session Management
- Role-Based Authentication

---

### 🎉 Events Module

Provides the core functionality of Nexvent.

**Features**
- Browse Event Packages
- Online Event Booking
- Event Categories
- Event Package Details
- Booking Confirmation
- Event Search & Filtering

---

### 🎨 Themes Module

Allows users to explore and select themes for different types of events.

**Available Themes**
- Wedding Themes
- Birthday Decorations
- Corporate Events
- Anniversary Celebrations
- Party Decorations
- Custom Event Themes

---

### 📊 Administration Module

Designed for administrators to efficiently manage platform operations.

**Features**
- User Management
- Event Package Management
- Theme Management
- Booking Management
- Feedback Management
- Dashboard Overview

## 🚀 Future Enhancements

The following improvements are planned for future releases:

- 💳 Online Payment Gateway Integration
- 📱 Mobile Application (Android & iOS)
- 🔔 Real-Time Booking Notifications
- 📅 Event Calendar Integration
- ⭐ Customer Ratings & Reviews
- 📍 Google Maps Venue Integration
- 🤖 AI-Based Event Recommendations
- 🐳 Docker Deployment
- 🐘 PostgreSQL Database Support
- 🌐 REST API for Mobile Applications

## 📄 License

This project is licensed under the MIT License.

See the **LICENSE** file for more information.

## 👨‍💻 Author

<div align="center">

### Abi Thomas

**Backend Developer | Python & Django Developer**

Passionate about building scalable backend systems, modern web applications, and developer-friendly software using Python and Django.

<p>

<a href="https://github.com/Aby020">
<img src="https://img.shields.io/badge/GitHub-Aby020-181717?logo=github">
</a>

<a href="https://linkedin.com/in/abithomas-dev">
<img src="https://img.shields.io/badge/LinkedIn-Abi%20Thomas-0A66C2?logo=linkedin">
</a>

</p>

</div>


## ⭐ Support

If you found this project helpful, please consider giving it a ⭐ on GitHub.

Your support motivates me to continue building and improving open-source projects.