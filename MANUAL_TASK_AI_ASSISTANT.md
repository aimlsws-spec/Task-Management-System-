# Manual Testing & User Task Guide: AI Task/Project Recommendation Engine

This document provides a comprehensive, step-by-step manual test guide and walkthrough for the new **AI-Powered Description and Special Note Recommendation Engine** with **Company Memory** in SeaWind Task Management System (TMS).

---

## 1. Feature Highlights
- **Zero-Cost Dual Cloud Engine:** Operates with $0.00 cost using Google Gemini Free API (1,500 free calls/day), OpenRouter Free Model Pool (`:free`), and built-in smart technical heuristic fallback.
- **Auto-Learning Company Memory ("What is Elala?"):** When an unknown custom product or term like *"Elala UI changes"* is entered, the AI prompts you once to explain what it is, saves it into company memory, and remembers it for all future tasks!
- **Generic Term Recognition:** Standard terms like *"HRMS"*, *"Task Management System"*, *"Payment Gateway Integration"*, *"OAuth2"*, or *"Bug in Login"* are recognized automatically without asking questions.
- **Effortless Assignee UX:** 1-click `[ Recommend with AI ]` button on Task and Project creation, preview with markdown formatting, one-click insertion (`[ Insert Both into Form ]`, `[ Insert Description only ]`, `[ Insert Special Note only ]`), and inline editing/customization.
- **Company Knowledge Management:** Owner and CEO can view, add, or delete remembered products anytime under Companies $\rightarrow$ `Manage Knowledge`.

---

## 2. Test Cases & Step-by-Step Manual Walkthrough

### Test Case 1: Generic Technical Term (e.g. HRMS Attendance)
**Objective:** Verify that generic technical/business terms generate instant structured descriptions and special notes without asking for context.

1. **Navigate to New Task:**
   - Log in as Owner, CEO, or Head (`owner@demo.example.com` / `Password123!`).
   - Click the **"Assign Task"** button in the top navigation bar or dashboard (URL: `/tasks/new`).
2. **Select Assignee:**
   - Pick any employee from the left panel (e.g., *Dev Lead* or *Alpha Dev*).
3. **Enter Generic Title:**
   - In the **Task title** field, type:
     ```
     HRMS employee attendance and leave module
     ```
4. **Click AI Assist:**
   - Click the **`✨ Recommend with AI`** button beside the title field.
5. **Observe Behavior:**
   - The AI Assistant modal opens with an animated loader (*"Analyzing title and company knowledge..."*).
   - Because *"HRMS"* is a recognized industry term, the AI **does NOT prompt for context**.
   - It directly displays:
     - **Recommended Description:** Formatted markdown with `### Objective`, `### Scope of Work` (bulleted deliverables), and `### Acceptance Criteria` with checkboxes `[ ]`.
     - **Recommended Special Note:** Technical caveats, QA edge cases, and testing precautions.
6. **Test Insertion & Customization:**
   - Edit a line directly inside the modal textarea (e.g. add a custom note).
   - Click **`[ ✨ Insert Both into Form ]`**.
   - Verify that the Description and Special Note fields in the task form are populated with the generated text.
   - You can continue typing or editing in the form before clicking *"Assign"*.

---

### Test Case 2: Unknown Brand/Product Learning Cycle (e.g. "Elala")
**Objective:** Verify that the AI detects an unknown product/system name, prompts the user to explain it, saves it to company memory, and uses it for future tasks.

#### Step A: First Encounter (Trigger Context Challenge)
1. In the **New Task** form (`/tasks/new`), type:
   ```
   Elala UI changes for mobile checkout
   ```
2. Click **`✨ Recommend with AI`**.
3. **Observe the Prompt:**
   - The AI detects that *"Elala"* is not in the company's knowledge base.
   - An interactive context card appears:
     > **"We haven't seen 'Elala' before"**  
     > *"Please provide a quick 1-line description of what 'Elala' is... The AI will remember it for all future tasks and projects in this company!"*
4. **Teach the AI:**
   - In the *"What is Elala?"* box, type:
     ```
     B2B jewelry eCommerce mobile app and admin portal
     ```
   - In the *"Tech Stack"* box, type:
     ```
     Flutter, Node.js, MySQL
     ```
   - Click **`[ ✓ Save to Company Memory & Generate ]`**.
5. **Observe Automatic Generation:**
   - The entity *"Elala"* is stored in the database for your company.
   - The AI immediately generates the Description and Special Note incorporating the jewelry eCommerce and Flutter context!
   - Click **`[ Insert Both into Form ]`**.

#### Step B: Subsequent Usage (Instant Recall Without Prompting)
1. Clear the title field and type a completely new task mentioning Elala:
   ```
   Elala product search filter bug
   ```
2. Click **`✨ Recommend with AI`**.
3. **Observe Result:**
   - The AI **does NOT ask what Elala is** this time!
   - It immediately generates a tailored bug resolution description referencing the Elala mobile app and jewelry catalog!

---

### Test Case 3: AI Recommendation in Project Creation
**Objective:** Verify that AI recommendation works seamlessly inside the Project creation modal.

1. Navigate to **Projects** (`/projects`).
2. Click **"+ New Project"**.
3. In the **Project name** field, type:
   ```
   Elala v2 Redesign
   ```
4. Click the **`✨ Recommend with AI`** button above the Project name input.
5. In the modal, verify the generated project description and special note.
6. Click **`[ Insert Both into Form ]`**.
7. Observe that *"What is this project about?"* and *"Special Note"* are filled instantly.

---

### Test Case 4: Company Knowledge Management (Owner / CEO)
**Objective:** Verify that leadership can view, add, and delete remembered company knowledge.

1. Navigate to **Companies** (`/companies`).
2. On any company card (e.g. *SeaWind Solution*), find the **"AI Knowledge & Memory"** section.
3. Click **`Manage Knowledge`**.
4. **In the Knowledge Modal:**
   - You will see the remembered entry for **"Elala"** with its description and tech stack.
   - Click **`+ Add Product / Entity`** to pre-teach the AI a new system:
     - Name: `FinTrack`
     - Description: `Internal employee expense reimbursement and accounting system`
     - Tech Stack: `Python, React, PostgreSQL`
     - Click **`Save Knowledge`**.
5. Now create a task with title *"FinTrack report export"* $\rightarrow$ click AI Assist $\rightarrow$ the AI already knows it is an expense accounting system!
6. In the Knowledge Modal, test deleting an entry using the trash icon.

---

### Test Case 5: Company Isolation (Multi-Company Boundary)
**Objective:** Verify that Company A's learned memory does not leak to Company B.

1. Under **Companies** (`/companies`), ensure you have a second company (e.g. *Delta Corp*).
2. Go to **New Task** (`/tasks/new`), and select **Delta Corp** in the Company dropdown.
3. Type:
   ```
   Elala UI changes
   ```
4. Click **`✨ Recommend with AI`**.
5. **Observe Result:**
   - Because Elala was learned under *SeaWind Solution*, Delta Corp does **NOT** have Elala in its memory.
   - The AI properly challenges Delta Corp: *"We haven't seen 'Elala' before"*, confirming 100% strict multi-company isolation!

---

## 3. Configuration & Environment Variables

The AI Assistant is configured in `backend/.env` (or Passenger environment):

| Variable | Description | Default |
|---|---|---|
| `TMS_GEMINI_API_KEY` | Google Gemini Free API key (get from [aistudio.google.com](https://aistudio.google.com) for $0.00) | `""` (If empty, falls back to OpenRouter or Heuristics) |
| `TMS_OPENROUTER_API_KEY` | OpenRouter Free API key (get from [openrouter.ai](https://openrouter.ai) for $0.00) | `""` (If empty, falls back to Heuristics) |
| `TMS_AI_OPENROUTER_MODELS` | Comma-separated list of fallback free models | `meta-llama/llama-3.3-70b-instruct:free,google/gemini-2.0-flash-exp:free,qwen/qwen-2.5-72b-instruct:free,meta-llama/llama-3.1-8b-instruct:free` |
| `TMS_AI_GEMINI_MODEL` | Gemini model identifier | `gemini-2.0-flash` |

*Note: Even without any API keys configured in `.env`, the system automatically uses the built-in smart technical heuristic fallback, so it never crashes and never fails to provide structured suggestions!*
