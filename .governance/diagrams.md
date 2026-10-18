# Framework diagrams

> Visual references for the governance framework. All diagrams are Mermaid — they render natively in GitHub, GitLab, Cursor, VS Code (with the Mermaid extension), and Obsidian. Use for onboarding, all-hands slides, or pinning in Slack.

---

## 1. The four-file mental model (bubble view)

```mermaid
flowchart TB
    classDef principle fill:#fef3c7,stroke:#d97706,color:#1c1917
    classDef human fill:#dbeafe,stroke:#2563eb,color:#1c1917
    classDef machine fill:#d1fae5,stroke:#059669,color:#1c1917
    classDef ai fill:#ede9fe,stroke:#7c3aed,color:#1c1917
    classDef gate fill:#fee2e2,stroke:#dc2626,color:#1c1917

    PHIL((Philosophy<br/>4 principles)):::principle

    CAP((Capability Spec<br/>feature area<br/>seniors author)):::human
    TASK((Task Card<br/>per Git issue<br/>juniors fill via form)):::human

    SCH1((Capability<br/>Schema)):::machine
    SCH2((Task Card<br/>Schema)):::machine
    TESTS((Contract Tests<br/>tests/contract/)):::machine

    AGENTS((AGENTS.md<br/>AI rules)):::ai

    CI((CI Gate<br/>governance.yml)):::gate

    PHIL -.guides.-> CAP
    PHIL -.guides.-> TASK
    CAP -->|"parent of"| TASK
    SCH1 -->|"validates"| CAP
    SCH2 -->|"validates"| TASK
    TASK -->|"references"| TESTS
    AGENTS -->|"injects into AI"| TASK
    AGENTS -->|"injects into AI"| CAP
    CI --> SCH1
    CI --> SCH2
    CI --> TESTS
```

**Reading it:** the **yellow bubble at the top** is the philosophy — it shapes everything. **Blue bubbles** are what humans write. **Green bubbles** are what machines read. **Purple bubble** is the AI integration point. **Red bubble** is the CI gate. Arrows show dependency.

---

## 2. Junior workflow (the happy path)

```mermaid
flowchart LR
    A[1\. Pick a task<br/>from the backlog] --> B[2\. Open issue<br/>fill the form]
    B --> C[3\. git checkout -b<br/>task/BBS-127]
    C --> D[4\. Open Cursor<br/>AI auto-loads<br/>task card]
    D --> E[5\. Implement with AI<br/>AI honors:<br/>- non_goals<br/>- do_not_modify<br/>- preferred_patterns]
    E --> F[6\. pytest tests/contract/<br/>-k task_id]
    F --> G{All listed<br/>contract tests<br/>pass?}
    G -->|no| E
    G -->|yes| H[7\. git push<br/>open PR]
    H --> I[CI runs governance.yml]
    I --> J{All gates<br/>green?}
    J -->|no| K[Read the failure<br/>fix the issue<br/>not the gate]
    K --> E
    J -->|yes| L[Reviewer assigned<br/>judgment only —<br/>no compliance check]
    L --> M[Merge]
```

**The junior never:** writes YAML by hand. Memorizes the framework. Worries about whether they "did governance." The form, the AI rules, and CI do that work.

---

## 3. Senior workflow (designing a capability)

```mermaid
flowchart TB
    A[Decide a new bounded<br/>area is needed] --> B[Author<br/>.governance/capabilities/<br/>&lt;name&gt;.yaml]
    B --> C[Define:<br/>contract.inputs<br/>contract.outputs<br/>contract.invariants]
    C --> D[Define:<br/>tasks_must.pass_contract_tests<br/>forbidden<br/>evidence_requirements]
    D --> E[Write the contract tests<br/>in tests/contract/]
    E --> F[Break capability into<br/>~3-5 task cards]
    F --> G[Assign task cards<br/>to juniors via Git issues]
    G --> H[Review PRs that<br/>land — judgment only,<br/>no compliance check]
    H --> I{Same compliance<br/>issue across<br/>multiple PRs?}
    I -->|yes| J[Add a new contract test<br/>or strengthen schema —<br/>not a Slack reminder]
    J --> E
    I -->|no| K[Capability evolves<br/>via task cards over time]
```

**The senior never:** spends review time on compliance. Writes the same correction twice without it becoming a contract test. Holds context in their head that the framework could hold for them.

---

## 4. What happens when an AI session starts

```mermaid
sequenceDiagram
    actor Junior
    participant Cursor as Cursor / Claude / Copilot
    participant Repo
    participant AI as LLM

    Junior->>Cursor: Open project, start session
    Cursor->>Repo: Read AGENTS.md
    Repo-->>Cursor: AI standing orders
    Cursor->>Repo: Read .governance/philosophy.md
    Repo-->>Cursor: The 4 principles

    Junior->>Cursor: "Help me implement issue BBS-127"
    Cursor->>Repo: Read task card from issue body / .governance/tasks/BBS-127.yaml
    Repo-->>Cursor: Task card YAML

    Cursor->>Repo: Read each path in ai_context.required_reading
    Repo-->>Cursor: parent capability + design docs + relevant code

    Cursor->>AI: System prompt = AGENTS.md + philosophy + task card + required reading
    Cursor->>AI: User prompt = junior's question

    AI->>Junior: Generates code respecting:<br/>- non_goals<br/>- do_not_modify<br/>- preferred_patterns<br/>- pointed at named contract tests

    Junior->>Cursor: Accept generated code
    Junior->>Repo: pytest tests/contract/ -k BBS-127
    Repo-->>Junior: Pass / fail
```

**Key insight:** by the time the AI sees the junior's question, the task card and all required reading are already in its context window. The AI cannot "forget" to honor the spec, because the spec is right there.

---

## 5. Entity relationships

```mermaid
erDiagram
    PHILOSOPHY ||--|{ CAPABILITY : "guides"
    CAPABILITY ||--|{ TASK_CARD : "parent_of"
    TASK_CARD ||--|{ CONTRACT_TEST : "references"
    CAPABILITY ||--|{ CONTRACT_TEST : "inherits"
    TASK_CARD ||--|| GIT_ISSUE : "is filed as"
    GIT_ISSUE ||--|{ PULL_REQUEST : "closes"
    PULL_REQUEST }|--|{ CONTRACT_TEST : "must pass"
    PULL_REQUEST }|--|| CI_RUN : "gated by"

    PHILOSOPHY {
        string principle_1
        string principle_2
        string principle_3
        string principle_4
    }
    CAPABILITY {
        string id PK
        string purpose
        string tier
        list contract_invariants
        list forbidden
    }
    TASK_CARD {
        string id PK
        string parent_capability FK
        string goal_bigger_picture
        list non_goals
        list contract_tests
        list required_reading
    }
    CONTRACT_TEST {
        string test_id PK
        string file_path
    }
```

---

## 6. What the team sees on a typical day

```mermaid
flowchart LR
    subgraph MORNING[Morning]
        A[Mansura<br/>files capability spec] --> B[Auto-creates<br/>task cards from form]
    end

    subgraph DAY[Daytime]
        C[Junior picks<br/>task BBS-127] --> D[AI reads task card<br/>+ required reading]
        D --> E[Junior + AI<br/>implement]
        E --> F[Contract tests<br/>pass locally]
        F --> G[PR opens]
        G --> H[CI gates run<br/>~3 minutes]
        H --> I[Reviewer judgment<br/>~10 minutes]
        I --> J[Merge]

        C2[Senior picks<br/>task BBS-128] --> D2[AI reads task card<br/>+ required reading]
        D2 --> E2[Senior + AI<br/>implement]
        E2 --> F2[Contract tests<br/>pass locally]
        F2 --> G2[PR opens]
        G2 --> H2[CI gates run<br/>~3 minutes]
        H2 --> I2[Reviewer judgment<br/>~10 minutes]
        I2 --> J2[Merge]
    end

    subgraph EVENING[Evening]
        K[Mansura reviews 4 PRs:<br/>compliance was a CI gate<br/>only judgment calls left] --> L[Approve, merge,<br/>or push back]
    end
```

**The lever:** reviewer time per PR drops from "read every line, check compliance" to "10 minutes of judgment." Multiplied across a team of 6 engineers shipping 8 PRs/week, that's the difference between drowning in reviews and managing a team.
