# Project Context: Flask Compute Marketplace
We are expanding an existing Flask project into a two-sided compute rental marketplace.
- **Sellers** list idle hardware (PC, GPU, Server) at an hourly rate.
- **Buyers** rent compute power. Sellers keep 100% of their asking price; platform fees are added on top for the Buyer at checkout.

# Technical Architecture & Constraints
- **Backend:** Flask (`app.py`). Do NOT introduce SQLAlchemy. Use the existing global `DATABASE` instance (`Database` class from `interfaces/databaseinterface.py`).
- **Database Operations:** Execute reads with `DATABASE.ViewQuery(sql, params)` and writes with `DATABASE.ModifyQuery(sql, params)`. Target database is `database/test.db`.
- **Authentication:** Utilize existing `session['userid']`, `session['name']`, and `session['permission']` checks.
- **Frontend:** HTML templates must extend `layout.html`. Maintain styling inside `static/css/custom.css`[cite: 4, 9].
- **Asynchronous Requests:** Use the custom JavaScript function `new_ajax_helper(url, callback, formobject, method)` from `static/js/new_ajax_helper.js` for AJAX.