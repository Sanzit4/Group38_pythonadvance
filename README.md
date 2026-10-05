# AI-Powered Organisational Expense Management System

A basic Flask web application for managing organisational expenses. The system uses a SQLite database, role-based access, AI-based expense categorisation, and unusual-expense detection.

## Running the Project

```bash
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Then open `http://127.0.0.1:5000` in a browser.

The database and seed data are created automatically when the application is first run.

## Configuration

Create a `.env` file and add your Hugging Face API token:

```env
HF_TOKEN=your_hugging_face_token
```

The token is used for AI-based expense categorisation. Do not upload or share your `.env` file.

## Demo Login Accounts

| Role | Email | Password |
|---|---|---|
| Admin | admin@company.com | admin123 |
| Manager | manager@company.com | manager123 |
| Employee | employee@company.com | employee123 |

## Main Features

- Login and role-based access for employees, managers, and admins.
- Employees can submit expenses using a description and amount.
- AI automatically categorises expenses.
- Unusual expenses are detected and flagged.
- Admins can configure the organisation-wide expense threshold.
- SQLite database for users, expenses, departments, approvals, and settings.
- Employees can view their expense history.
- Managers can approve or reject expenses in their department.
- Admins can review all expenses and manage users and departments.
- Admins can view spending reports by category, department, and month.
- Managers can manage employees in their own department.

## AI Expense Categorisation

The system uses the Hugging Face Inference API with the `facebook/bart-large-mnli` zero-shot classification model.

Expenses are categorised into areas such as:

- Travel
- Meals & Entertainment
- Office Supplies
- Software & Subscriptions
- Utilities
- Marketing
- Professional Services
- Equipment
- Training & Education
- Other

If the AI service is unavailable, the expense is categorised as `Other`.

## Project Structure

```text
expense_system/
├── app.py
├── database.py
├── categorizer.py
├── requirements.txt
├── .env.example
├── .gitignore
└── templates/
```

## Security Notes

- Do not upload `.env` files or API tokens to GitHub.
- Demo passwords should be changed before real deployment.
- The development secret key should be replaced with a secure environment variable in production.
- Flask debug mode should be disabled in production.

## Future Improvements

- Local or fine-tuned AI categorisation.
- Charts and visual reports.
- PDF and Excel report exports.
- Receipt OCR.
- Email notifications.
- Monthly department budgets.
