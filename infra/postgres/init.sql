-- Create tables
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    account_type VARCHAR(50) DEFAULT 'standard',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS issues (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    title VARCHAR(500) NOT NULL,
    status VARCHAR(50) DEFAULT 'open',
    priority VARCHAR(50) DEFAULT 'medium',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS issue_updates (
    id SERIAL PRIMARY KEY,
    issue_id INTEGER REFERENCES issues(id),
    update_text TEXT NOT NULL,
    created_by VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS next_actions (
    id SERIAL PRIMARY KEY,
    issue_id INTEGER REFERENCES issues(id),
    action_text TEXT NOT NULL,
    assigned_to VARCHAR(255),
    due_date DATE,
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_roles (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Seed data
INSERT INTO customers (name, email, account_type) VALUES
    ('Acme Corp', 'contact@acmecorp.com', 'enterprise'),
    ('TechStart Ltd', 'hello@techstart.io', 'standard'),
    ('Global Finance Inc', 'support@globalfinance.com', 'enterprise'),
    ('RetailCo', 'ops@retailco.com', 'standard'),
    ('HealthPlus', 'admin@healthplus.org', 'premium');

INSERT INTO issues (customer_id, title, status, priority) VALUES
    (1, 'API integration failing intermittently', 'resolved', 'high'),
    (1, 'Invoice discrepancy for Q2 2025', 'open', 'medium'),
    (2, 'Onboarding documentation unclear', 'open', 'low'),
    (3, 'Data export not completing', 'open', 'critical'),
    (3, 'User permissions not applying correctly', 'open', 'high'),
    (4, 'Slow dashboard loading times', 'open', 'medium'),
    (5, 'Integration with third party system broken', 'open', 'high');

INSERT INTO issue_updates (issue_id, update_text, created_by) VALUES
    (1, 'Customer reported API errors starting 3 days ago. Logs reviewed.', 'support_team'),
    (1, 'Identified rate limiting issue in middleware. Fix in progress.', 'dev_team'),
    (2, 'Customer sent invoice from June. Finance team reviewing.', 'support_team'),
    (3, 'Export job times out after 30 minutes for large datasets.', 'support_team'),
    (4, 'Database query optimisation required. Assigned to backend team.', 'dev_team'),
    (5, 'Third party API changed authentication method. Update required.', 'dev_team');

INSERT INTO next_actions (issue_id, action_text, assigned_to, due_date, status) VALUES
    (1, 'Deploy rate limiting fix to production', 'dev_team', '2025-07-15', 'pending'),
    (2, 'Schedule call with finance team and customer', 'support_team', '2025-07-12', 'pending'),
    (3, 'Implement pagination for large data exports', 'dev_team', '2025-07-18', 'pending'),
    (5, 'Update OAuth credentials with new third party tokens', 'dev_team', '2025-07-11', 'pending');

INSERT INTO user_roles (username, role) VALUES
    ('alice', 'sales_user'),
    ('bob', 'support_user'),
    ('carol', 'admin');
-- Additional issue updates for richer demo data
INSERT INTO issue_updates (issue_id, update_text, created_by) VALUES
(2, 'Finance team reviewed the discrepancy - awaiting sign off from CFO', 'bob'),
(3, 'Documentation team assigned - first draft due Friday', 'carol'),
(4, 'Backend team identified root cause - database query optimisation needed', 'bob'),
(4, 'Fix deployed to staging - testing in progress', 'carol'),
(5, 'Third party vendor contacted - awaiting response', 'bob'),
(6, 'Performance profiling completed - CDN caching issue identified', 'bob'),
(7, 'API credentials rotated - testing new integration', 'carol');

-- Additional next actions for demo
INSERT INTO next_actions (issue_id, action_text, assigned_to, due_date) VALUES
(2, 'Schedule CFO sign off meeting', 'alice', '2025-08-01'),
(4, 'Deploy fix to production after staging tests pass', 'bob', '2025-07-25'),
(6, 'Implement CDN caching for dashboard assets', 'bob', '2025-07-30'),
(7, 'Complete integration testing with new API credentials', 'bob', '2025-07-28');
