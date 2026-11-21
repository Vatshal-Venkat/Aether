# Graph Report - Aether  (2026-11-21)

## Corpus Check
- 220 files · ~123,967 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 9 file(s) not represented in the graph (top: .css 4, .csv 3, (none) 1)

## Summary
- 2108 nodes · 5589 edges · 133 communities (96 shown, 37 thin omitted)
- Extraction: 92% EXTRACTED · 8% INFERRED · 0% AMBIGUOUS · INFERRED: 426 edges (avg confidence: 0.89)
- Token cost: 402,895 input · 0 output

## Community Hubs (Navigation)
- Accuracy Test Harness
- Health Checks & RLS Identity
- Merge, Ties & Extremes
- Schema Catalog
- Glossary Column Hints
- Frontend Dependencies
- Streaming & Pipeline Tests
- Frontend API Types & Conversation
- Conversation Runner & Follow-ups
- Reranker & Label Chunks
- Billing Row Filter
- LangGraph Wiring & Edges
- Number Verification
- Chat & Catalog API Routes
- FastAPI App & Endpoints
- Answer Writing Tests
- SQL Writer & RAG Tests
- Router & Privacy Check
- Answer Card UI
- Ops Routes (Audit, Metrics, Rate Limit)
- SQL Execution
- Patient & Doctor Lookups
- Accuracy Test Questions
- SQL Safety Tests
- Synthea Data Loading
- Saved Queries Store
- Plan Steps & Query Loop
- Answer Cache & Rate Limiter
- AI Model Fallback Chain
- AI Provider Setup
- App Settings
- AI Client & Daily Limits
- openFDA Label Fetching
- Drug Spelling Suggestions
- Automatic Charts
- Pipeline Deps & Row Filter Step
- Service Layer & Memory Saving
- Database Setup Script
- Frontend API Client
- Status Orb & Patient Picker
- Two-Database Planning Tests
- SQL Safety Checker
- Conversation Memory Store
- SQL Generation Step
- Query Planning
- Drug Label Store Tests
- Glossary Tables
- Label Retrieval Step
- Audit Log
- Project Brief Concepts
- Reworded Question Tests
- Web UI Design & Plan
- TypeScript Config
- Model Usage Ledger
- Aether Feature List
- Project Docs & Setup
- Service Layer Tests
- 2026-11-17-Plan-1-Foundation-Clinical-Chat (small)
- 2026-11-18-Plan-6-Accuracy-Report (small)
- Test Ties (small)
- Saved Queries (small)
- 2026-11-17-Healthcare-Multidb-Chatbot-Design (small)
- Synthesize (small)
- Saved Queries (small)
- Usetheme (small)
- Store (small)
- Runner (small)
- Cache.Py (small)
- Test Model Notice (small)
- Test Usage (small)
- Contextualize (small)
- How-It-Works (small)
- Build Drug Index (small)
- State (small)
- Rag/Store.Py (small)
- Test Config (small)
- 2026-11-18-Plan-5-Production-Habits (small)
- Csv (small)
- Test Chunking (small)
- Brief Features (small)
- How-It-Works (small)
- How-It-Works (small)
- 2026-11-17-Plan-3-Drug-Labels-Rag (small)
- Glossary (small)
- Brief Features (small)
- How-It-Works (small)
- App.Test (small)
- Brief Features (small)
- How-It-Works (small)
- Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)
- How-It-Works (small)
- How-It-Works (small)
- Fakes (small)
- Backendtarget (small)
- Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)
- How-It-Works (small)
- Brief Features (small)
- Brief Features (small)
- 2026-11-17-Healthcare-Multidb-Chatbot-Design (small)
- Simple Replies (small)
- Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)
- 2026-11-17-Plan-2-Second-Database-Cross-Db (small)
- Brief Features (small)
- Test Row Filter (small)
- Brief Features (small)
- Requirements (small)
- Requirements (small)
- Requirements (small)
- Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)
- Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)
- Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)
- Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)
- Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)
- Verification-Worksheet (small)

## God Nodes (most connected - your core abstractions)
1. `ScriptedLLM` - 158 edges
2. `make_deps()` - 117 edges
3. `Deps` - 73 edges
4. `run_chat()` - 61 edges
5. `ChatState` - 59 edges
6. `Settings` - 50 edges
7. `ChatResult` - 50 edges
8. `QueryResult` - 45 edges
9. `get_settings()` - 42 edges
10. `columns` - 41 edges

## Surprising Connections (you probably didn't know these)
- `Reworded question matching (embedding score + word check)` --references--> `match_kind()`  [INFERRED]
  docs/how-it-works.md → backend/app/memory/saved_queries.py
- `Assumption confirmation (ask instead of assume)` --references--> `with_assumptions()`  [INFERRED]
  docs/how-it-works.md → backend/app/memory/saved_queries.py
- `Saved queries (deterministic SQL reuse)` --references--> `SavedQueryStore`  [INFERRED]
  docs/how-it-works.md → backend/app/memory/saved_queries.py
- `MySQL sqlglot row-filter rewrite` --references--> `restrict_tables()`  [INFERRED]
  docs/superpowers/specs/2026-11-17-healthcare-multidb-chatbot-design.md → backend/app/safety/row_filter.py
- `Service layer around the pipeline (service.py)` --references--> `ChatService`  [INFERRED]
  docs/how-it-works.md → backend/app/service.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Patient privacy enforcement layers** — docs_how_it_works_router, docs_how_it_works_patient_name_guard, docs_how_it_works_row_level_security, docs_how_it_works_rls_signature, docs_how_it_works_mysql_query_rewrite, docs_how_it_works_hidden_totals, docs_how_it_works_safety_inspector, docs_how_it_works_chatbot_ro [EXTRACTED 1.00]
- **Question pipeline flow (recall to number check)** — docs_how_it_works_contextualize_step, docs_how_it_works_router, docs_how_it_works_cross_database_plan, docs_how_it_works_safety_inspector, docs_how_it_works_sql_retry, docs_how_it_works_merge_step, docs_how_it_works_number_check [EXTRACTED 1.00]
- **Code-enforced answer correctness checks** — docs_how_it_works_number_check, docs_how_it_works_extremes_check, docs_how_it_works_row_meaning, docs_how_it_works_tie_aware_limit, docs_how_it_works_saved_queries [INFERRED 0.85]
- **Patient privacy defense layers** — docs_superpowers_specs_2026_11_17_healthcare_multidb_chatbot_design_read_only_accounts, docs_superpowers_specs_2026_11_17_healthcare_multidb_chatbot_design_postgres_row_level_security, docs_superpowers_specs_2026_11_17_healthcare_multidb_chatbot_design_mysql_row_filter_rewrite, docs_superpowers_specs_2026_11_17_healthcare_multidb_chatbot_design_pii_exclusion, docs_superpowers_specs_2026_11_17_healthcare_multidb_chatbot_design_population_columns_hidden, docs_superpowers_plans_2026_11_17_plan_2_second_database_cross_db_signed_identity [INFERRED 0.85]
- **State scoped to (role, patient) for privacy** — docs_superpowers_plans_2026_11_18_plan_4_conversation_conversation_store, docs_superpowers_plans_2026_11_18_plan_5_production_habits_scoped_lru_cache, docs_superpowers_plans_2026_11_18_plan_5_production_habits_result_pages [INFERRED 0.85]
- **Aether milestone implementation plans** — docs_superpowers_plans_2026_11_17_plan_1_foundation_clinical_chat, docs_superpowers_plans_2026_11_17_plan_2_second_database_cross_db, docs_superpowers_plans_2026_11_17_plan_3_drug_labels_rag, docs_superpowers_plans_2026_11_18_plan_4_conversation, docs_superpowers_plans_2026_11_18_plan_5_production_habits, docs_superpowers_plans_2026_11_18_plan_6_accuracy_report [EXTRACTED 1.00]
- **Full-suite Aether accuracy runs (46-50 questions)** — docs_eval_2026_11_18_1225_groq_openai_gpt_oss_120b, docs_eval_2026_11_19_1540_groq_openai_gpt_oss_120b, docs_eval_2026_11_19_1706_groq_openai_gpt_oss_20b [INFERRED 0.85]
- **Targeted Aether re-runs of failing categories** — docs_eval_2026_11_18_1444_groq_openai_gpt_oss_120b, docs_eval_2026_11_18_1453_groq_openai_gpt_oss_120b, docs_eval_2026_11_18_1606_groq_openai_gpt_oss_20b, docs_eval_2026_11_19_1558_groq_openai_gpt_oss_120b [INFERRED 0.75]
- **Conversation follow-up questions handled via contextualize/clarify** — backend_app_eval_questions_cv02, backend_app_eval_questions_cv03, docs_eval_2026_11_18_1606_groq_openai_gpt_oss_20b_contextualize_step, docs_eval_2026_11_18_1606_groq_openai_gpt_oss_20b_clarify_step [INFERRED 0.75]
- **Multi-DB NL-to-SQL pipeline (router to formatter)** — building_a_multi_database_chatbot_structured_data_query_rag_2026_router, building_a_multi_database_chatbot_structured_data_query_rag_2026_schema_injector, building_a_multi_database_chatbot_structured_data_query_rag_2026_sql_generator, building_a_multi_database_chatbot_structured_data_query_rag_2026_sql_executor, building_a_multi_database_chatbot_structured_data_query_rag_2026_self_correction, building_a_multi_database_chatbot_structured_data_query_rag_2026_result_synthesizer, building_a_multi_database_chatbot_structured_data_query_rag_2026_response_formatter [EXTRACTED 1.00]
- **Aether LangGraph answer pipeline steps** — backend_docs_brief_features_understand_step, backend_docs_brief_features_route_step, backend_docs_brief_features_plan_write_sql, backend_docs_brief_features_check_and_fix, backend_docs_brief_features_answer_step, backend_docs_brief_features_verify_numbers [EXTRACTED 1.00]
- **Aether privacy and safety controls** — backend_docs_brief_features_read_only_access, backend_docs_brief_features_patient_view, backend_docs_brief_features_other_patients_refusal, backend_docs_brief_features_off_topic_decline, backend_docs_brief_features_env_secrets [EXTRACTED 1.00]

## Communities (133 total, 37 thin omitted)

### Community 0 - "Accuracy Test Harness"
Cohesion: 0.05
Nodes (62): EvalCase, Gold, load_cases(), compute_gold(), _run(), CaseScore, date_in(), _decimals() (+54 more)

### Community 1 - "Health Checks & RLS Identity"
Cohesion: 0.06
Nodes (39): health(), get_settings(), check_db(), get_engine(), identity_signature(), set_query_context(), rules_version(), db (+31 more)

### Community 2 - "Merge, Ties & Extremes"
Cohesion: 0.06
Nodes (45): _index(), merge_results(), tie_note(), QueryResult, _claimed(), extremes_note(), _fmt(), _is_number() (+37 more)

### Community 3 - "Schema Catalog"
Cohesion: 0.07
Nodes (27): is_id_column(), build_catalog(), Catalog, _category_values(), ColumnInfo, TableInfo, _matching_terms(), Glossary (+19 more)

### Community 4 - "Glossary Column Hints"
Cohesion: 0.05
Nodes (41): columns, allergies.severity1, claims.outstanding1, claims.outstandingp, claims.patientid, claims.providerid, claims_transactions.amount, claims_transactions.outstanding (+33 more)

### Community 5 - "Frontend Dependencies"
Cohesion: 0.06
Nodes (40): dependencies, @fontsource-variable/inter@5.3.0, @fontsource-variable/jetbrains-mono@5.3.0, motion@14.14.0, react@19.3.1, react-dom@19.3.1, devDependencies, jsdom@27.4.0 (+32 more)

### Community 6 - "Streaming & Pipeline Tests"
Cohesion: 0.11
Nodes (30): stream_chat(), ScriptedLLM, _ask(), engine(), _run(), test_billing_only_question(), test_clinician_refusal_does_not_mention_patient_mode(), test_cross_db_doctor_name() (+22 more)

### Community 7 - "Frontend API Types & Conversation"
Cohesion: 0.11
Nodes (30): AnswerKind, ChatRequest, ChatResult, DocumentRef, Progress, ResultPage, Role, Step (+22 more)

### Community 8 - "Conversation Runner & Follow-ups"
Cohesion: 0.13
Nodes (25): _initial_state(), run_chat(), engine(), _Library, memory(), remember(), test_a_question_that_needs_an_assumption_is_asked_back_not_guessed(), test_assumption_text_is_tidied() (+17 more)

### Community 9 - "Reranker & Label Chunks"
Cohesion: 0.10
Nodes (15): load_reranker(), model_cached(), _onnx_scorer(), score(), Reranker, Chunk, by_keyword(), chunk() (+7 more)

### Community 10 - "Billing Row Filter"
Cohesion: 0.13
Nodes (22): _condition(), restrict_tables(), RowFilter, UnsafeValueError, run(), test_alias_kept(), test_cte_body(), test_cte_named_like_table() (+14 more)

### Community 11 - "LangGraph Wiring & Edges"
Cohesion: 0.16
Nodes (22): build_graph(), after_execute(), after_merge(), after_next_step(), after_row_filter(), after_validate(), _last_error(), _retry_or_fail() (+14 more)

### Community 12 - "Number Verification"
Cohesion: 0.12
Nodes (27): _allowed_numbers(), _cells(), _drop_rank_columns(), find_unverified_numbers(), _matches(), _numbers_in_text(), _value(), check() (+19 more)

### Community 13 - "Chat & Catalog API Routes"
Cohesion: 0.09
Nodes (10): patients(), schema(), chat(), chat_stream(), ChatRequest, _check_patient(), model_usage(), session_history() (+2 more)

### Community 14 - "FastAPI App & Endpoints"
Cohesion: 0.07
Nodes (9): get_runner(), get_stream_runner(), create_app(), lifespan(), _db_down(), test_chat_503_when_pipeline_unavailable(), test_chat_patient_check_503_when_db_down(), test_patients_503_when_db_down() (+1 more)

### Community 15 - "Answer Writing Tests"
Cohesion: 0.18
Nodes (28): synthesize(), _correction(), verify_numbers(), make_deps(), test_numbers_inside_citation_labels_are_not_flagged(), test_verify_numbers_accepts_excerpt_numbers(), _state(), test_a_sampled_table_comes_with_code_computed_extremes() (+20 more)

### Community 16 - "SQL Writer & RAG Tests"
Cohesion: 0.15
Nodes (26): test_generate_sql_appends_attempt(), test_generate_sql_patient_mode_says_rows_are_prefiltered(), test_generate_sql_retry_includes_previous_error(), test_route_prompt_mentions_patient_rules_in_patient_mode(), ask(), route(), SpyReranker, test_boxed_warning_question_searches_that_section() (+18 more)

### Community 17 - "Router & Privacy Check"
Cohesion: 0.11
Nodes (21): extract_sql(), names_another_patient(), route(), RouteDecision, route_system(), assumption_accepted(), similar_ask_reply(), with_assumptions() (+13 more)

### Community 18 - "Answer Card UI"
Cohesion: 0.12
Nodes (21): base, AnswerCard(), cleanAnswer(), KIND_LABEL, LabelList(), SqlList(), Timeline(), Disclosures() (+13 more)

### Community 19 - "Ops Routes (Audit, Metrics, Rate Limit)"
Cohesion: 0.11
Nodes (9): audit(), get_ops(), metrics(), rate_limit(), result_page(), Ops, Metrics, test_metrics_counts_and_renders() (+1 more)

### Community 20 - "SQL Execution"
Cohesion: 0.13
Nodes (22): execute(), json_safe(), _attempt(), _exec(), _exec_billing(), test_empty_result_does_not_retry(), test_execute_db_error_recorded(), test_execute_falls_back_when_the_tie_query_fails() (+14 more)

### Community 21 - "Patient & Doctor Lookups"
Cohesion: 0.12
Nodes (15): _begin(), list_patients(), list_provider_names(), patient_exists(), build_deps(), _final_sql(), _minutes(), model_notice() (+7 more)

### Community 22 - "Accuracy Test Questions"
Cohesion: 0.16
Nodes (27): CL08 Most recent HbA1c value for a named patient, CL10 Which diagnosis affects the most patients?, CL11 How many patients have diabetes?, CV02 Insurers (follow-up), CV03 How many of them are female?, HY03 What is my metformin used for?, PT01 When was my last visit?, RG04 Can naproxen be taken with lisinopril? (+19 more)

### Community 23 - "SQL Safety Tests"
Cohesion: 0.14
Nodes (25): assert_rejected(), check(), test_accepts_cte_and_join(), test_accepts_simple_select(), test_adds_limit(), test_alias_named_like_another_table_cannot_hide_pii(), test_aliased_tables_still_work(), test_allows_common_postgres_functions() (+17 more)

### Community 24 - "Synthea Data Loading"
Cohesion: 0.13
Nodes (9): download_synthea(), _find_csv_folder(), load_table(), sql_dtypes(), test_date_only_columns_become_plain_dates(), test_download_skips_when_present(), test_load_table_lowercases_and_parses_dates(), test_sql_dtypes_id_columns_are_varchar64() (+1 more)

### Community 25 - "Saved Queries Store"
Cohesion: 0.16
Nodes (17): _save_query(), normalize_question(), SavedQuery, SavedSql, worth_saving(), ask(), saved(), test_a_saved_query_that_no_longer_works_is_rewritten_and_replaced() (+9 more)

### Community 26 - "Plan Steps & Query Loop"
Cohesion: 0.20
Nodes (22): PlanStep, _attempt(), engines(), _run_filter_and_execute(), _state(), _step1_result(), test_key_column_present_ok(), test_missing_key_column_is_error() (+14 more)

### Community 27 - "Answer Cache & Rate Limiter"
Cohesion: 0.12
Nodes (8): TTLCache, SlidingWindow, ResultStore, Clock, test_cache_hit_miss_ttl_and_lru(), test_result_pages_and_scoping(), test_sliding_window(), test_rate_limit_429()

### Community 28 - "AI Model Fallback Chain"
Cohesion: 0.16
Nodes (15): build_chain(), chat_models(), track_models(), Clock, Model, _rate_limit(), _settings(), test_daily_limit_moves_to_the_fallback_without_retrying() (+7 more)

### Community 29 - "AI Provider Setup"
Cohesion: 0.12
Nodes (13): get_chat_model(), LLMConfigError, LLMOutputError, make_provider(), _provider_models(), Decision, _settings(), test_ask_json_gives_up() (+5 more)

### Community 30 - "App Settings"
Cohesion: 0.13
Nodes (6): Settings, main(), server_options(), test_rls_key_derived_when_unset(), test_port_can_be_overridden_on_the_command_line(), test_server_options_use_the_configured_port()

### Community 31 - "AI Client & Daily Limits"
Cohesion: 0.11
Nodes (9): _content(), daily_limit_rest(), _extract_json(), _resting(), call(), _tokens(), _transient_errors(), limit_numbers() (+1 more)

### Community 32 - "openFDA Label Fetching"
Cohesion: 0.16
Nodes (12): fetch_label(), ingredient_of(), label_sections(), _query(), _client(), test_fetch_falls_back_to_exact_generic_name(), test_fetch_miss_cached(), test_fetch_reads_cache() (+4 more)

### Community 33 - "Drug Spelling Suggestions"
Cohesion: 0.17
Nodes (12): _replace(), SpellingSuggestion, suggest_drug_spelling(), _vocabulary(), similarity(), trigrams(), test_capitalised_and_trailing_punctuation(), test_correct_spelling_and_ordinary_words_are_left_alone() (+4 more)

### Community 34 - "Automatic Charts"
Cohesion: 0.18
Nodes (17): QueryResult, Bars(), Chart(), Line(), ChartPoint, ChartSpec, chartSpec(), compact() (+9 more)

### Community 35 - "Pipeline Deps & Row Filter Step"
Cohesion: 0.19
Nodes (12): Deps, _link_values(), row_filter(), validate(), _assert_only_own(), billing_setup(), deps_and_patient(), _run_billing() (+4 more)

### Community 36 - "Service Layer & Memory Saving"
Cohesion: 0.19
Nodes (7): ChatResult, _remember(), ChatService, client(), fake_runner(), stream_client(), fake_stream()

### Community 37 - "Database Setup Script"
Cohesion: 0.16
Nodes (12): apply_postgres_rls(), create_databases(), create_readonly_users(), load_tables(), main(), _server_url(), _sql_literal(), _statements() (+4 more)

### Community 38 - "Frontend API Client"
Cohesion: 0.19
Nodes (14): ApiError, askChat(), askChatStream(), getHealth(), getPatients(), getResultPage(), getUsage(), messageFor() (+6 more)

### Community 39 - "Status Orb & Patient Picker"
Cohesion: 0.18
Nodes (14): Health, Patient, Props, StatusOrb(), PatientPicker(), Props, RolePill(), ROLES (+6 more)

### Community 40 - "Two-Database Planning Tests"
Cohesion: 0.14
Nodes (17): merge_dicts(), _norm(), _state(), test_bad_plans_rejected(), test_clinician_naming_patients_is_fine(), test_full_name_of_patient_sharing_a_doctor_surname_still_refused(), test_link_oriented_to_first_step(), test_link_whitespace_tolerated() (+9 more)

### Community 41 - "SQL Safety Checker"
Cohesion: 0.13
Nodes (11): _fail(), _function_names(), _real_tables(), tables_in(), validate_sql(), ValidationResult, test_alias_collision_cannot_hide_population_columns(), test_allows_common_mysql_functions() (+3 more)

### Community 42 - "Conversation Memory Store"
Cohesion: 0.23
Nodes (10): ConversationStore, Turn, test_a_follow_up_is_reused_by_previous_question_plus_what_was_typed(), test_history_oldest_first_and_limited(), test_history_scoped_to_role_and_patient(), test_long_answers_are_truncated(), test_only_answers_and_clarifications_are_context(), test_survives_reopen() (+2 more)

### Community 43 - "SQL Generation Step"
Cohesion: 0.18
Nodes (9): generate_sql(), hybrid_notes(), link_notes(), inject_schema(), _words(), current_step(), is_multi_step(), sql_system() (+1 more)

### Community 44 - "Query Planning"
Cohesion: 0.16
Nodes (10): _norm_link(), normalize_plan(), plan(), saved_queries_version(), Link, QueryPlan, plan_system(), Plan 2 Second Database + Cross-DB Questions (+2 more)

### Community 45 - "Drug Label Store Tests"
Cohesion: 0.15
Nodes (9): LabelSection, FakeEmbedding, test_rag_prompt_delimits_excerpts(), _named(), store(), test_drug_matching_is_not_over_eager(), test_drugs_in_text(), test_search_filtered_by_drug() (+1 more)

### Community 46 - "Glossary Tables"
Cohesion: 0.11
Nodes (19): tables, allergies, careplans, claims, claims_transactions, conditions, devices, encounters (+11 more)

### Community 47 - "Label Retrieval Step"
Cohesion: 0.16
Nodes (9): _pool(), retrieve(), _row_medicines(), _search(), section_of(), _section_phrase(), timed(), decorator() (+1 more)

### Community 48 - "Audit Log"
Cohesion: 0.24
Nodes (7): AuditEntry, AuditLog, entry(), test_audit_entry_from_result(), test_audit_file_is_only_created_when_first_used(), test_audit_roundtrip_newest_first(), test_first_audit_writes_at_the_same_time_are_all_kept()

### Community 49 - "Project Brief Concepts"
Cohesion: 0.18
Nodes (9): Building a Multi-Database Chatbot (Structured Data Query + RAG) - 2026, Data Catalog / Business Glossary, Data Virtualization, Production-Readiness Checklist, Response Formatter, Result Synthesizer, SQL Executor (read-only), Query Generator (LLM SQL writer) (+1 more)

### Community 50 - "Reworded Question Tests"
Cohesion: 0.20
Nodes (11): engine(), FakeEmbed, _key(), test_a_less_certain_one_asks_first_and_costs_no_ai_call(), test_a_negation_is_never_matched(), test_a_very_close_rewording_reuses_the_saved_query_and_says_how_it_was_read(), test_no_answers_it_fresh_and_never_asks_again(), test_patients_are_only_offered_their_own_earlier_questions() (+3 more)

### Community 51 - "Web UI Design & Plan"
Cohesion: 0.18
Nodes (10): UI Web Front End Implementation Plan, AnswerCard with disclosures (SQL, Table, Labels, Timeline), Typed API client with error mapping, usePhases pipeline phase captions, useChat hook (late-answer discard via AbortController + generation counter), Aether Web UI Design, prefers-reduced-motion support, Backend status orb (polls /health every 15 s) (+2 more)

### Community 52 - "TypeScript Config"
Cohesion: 0.12
Nodes (16): compilerOptions, allowImportingTsExtensions, isolatedModules, jsx, lib, module, moduleResolution, noEmit (+8 more)

### Community 53 - "Model Usage Ledger"
Cohesion: 0.19
Nodes (5): UsageLedger, call(), test_a_model_resting_in_the_ledger_is_skipped(), test_chain_writes_usage_and_limits_to_the_ledger(), _usage_model()

### Community 54 - "Aether Feature List"
Cohesion: 0.20
Nodes (14): Answer step, Check and fix (validate + retry up to 3), Clarifying questions with clickable options, Conversation memory (per conversation, role, patient), LangGraph question pipeline, Off-topic and harmful request decline, Plan and write SQL step, Role switch (clinician / view as patient) (+6 more)

### Community 55 - "Project Docs & Setup"
Cohesion: 0.15
Nodes (14): langchain-groq / langchain-google-genai / langchain-ollama, How Aether Works (plain-language guide), Aether health-data chatbot, billing_db (MySQL billing/insurers/doctors), clinical_db (PostgreSQL medical records), LLM gateway (Groq default, Gemini/Ollama, JSON mode), Synthea synthetic patient data, Free AI keys (Groq, Gemini, Ollama) (+6 more)

### Community 56 - "Service Layer Tests"
Cohesion: 0.33
Nodes (13): answer(), counting_runner(), svc(), test_big_tables_come_in_pages(), test_cache_hit_is_audited_and_remembered(), test_cache_scoped_to_role_and_patient(), test_clinician_patient_id_is_ignored(), test_followups_bypass_cache() (+5 more)

### Community 57 - "2026-11-17-Plan-1-Foundation-Clinical-Chat (small)"
Cohesion: 0.16
Nodes (11): Plan 1 Foundation + Clinical Chat, scripts/ask.py live smoke CLI, ChatState graph state, Deps dataclass (settings, llm, catalog, glossary, engines), Identity switching via set_config inside a query, Pluggable LLM client with retry and fallbacks, Schema catalog (introspection, PII dropped), setup_databases.py (download, load, chatbot_ro, RLS) (+3 more)

### Community 58 - "2026-11-18-Plan-6-Accuracy-Report (small)"
Cohesion: 0.17
Nodes (12): Plan 4 Conversation: Follow-ups, Clarification, Streaming, clarify route with option chips, contextualize node (follow-up to standalone question), 'Understood as' line for follow-ups, Plan 6 Accuracy Report (Evaluation Harness), Dated accuracy report (docs/eval), EvalCase question set (questions.yaml, ~42 cases), /api/chat/stream Server-Sent Events (+4 more)

### Community 59 - "Test Ties (small)"
Cohesion: 0.21
Nodes (7): _order_key(), with_ties(), _sql(), test_left_alone(), test_ordinal_order_key_is_resolved(), test_top_n_becomes_rank_with_ties(), test_unparseable_sql_is_left_alone()

### Community 60 - "Saved Queries (small)"
Cohesion: 0.16
Nodes (4): SavedQueryStore, main(), engine(), store()

### Community 61 - "2026-11-17-Healthcare-Multidb-Chatbot-Design (small)"
Cohesion: 0.23
Nodes (10): Glossary model (tables, columns, terms, pii_columns, join_keys), Left-join merge of step results, Aether Healthcare Multi-DB Chatbot Design, Aether chatbot, MySQL billing_db, PostgreSQL clinical_db, MySQL sqlglot row-filter rewrite, PostgreSQL native Row-Level Security (+2 more)

### Community 62 - "Synthesize (small)"
Cohesion: 0.20
Nodes (6): draft_answer(), _excerpts(), _results_table(), _sql_that_ran(), _problems(), _unverified()

### Community 63 - "Saved Queries (small)"
Cohesion: 0.20
Nodes (7): _cosine(), Match, match_kind(), _opposed(), _words(), test_match_kind_guards(), test_match_kind_on_measured_scores()

### Community 64 - "Usetheme (small)"
Cohesion: 0.27
Nodes (7): App(), Composer(), useChat(), useHealth(), stored(), useTheme(), react

### Community 65 - "Store (small)"
Cohesion: 0.23
Nodes (5): check_drug_labels(), DrugLabelStore, _norm(), test_open_missing_returns_none(), test_reopen_persists()

### Community 66 - "Runner (small)"
Cohesion: 0.22
Nodes (8): friendly_error(), is_rate_limit(), _log_failure(), DailyLimitReached, test_daily_limit_message_says_how_long_to_wait(), test_rate_limit_is_logged_in_one_line_without_a_traceback(), invoke(), test_when_every_model_is_out_the_user_sees_the_rate_limit_message()

### Community 68 - "Test Model Notice (small)"
Cohesion: 0.31
Nodes (8): _deps(), engine(), _limit(), _model(), test_all_models_out_says_so_and_when_the_first_is_back(), test_no_notice_when_the_main_model_answers(), test_notice_when_a_backup_model_answers(), test_streamed_answers_carry_the_notice_too()

### Community 69 - "Test Usage (small)"
Cohesion: 0.37
Nodes (9): Clock, _ledger(), _row(), test_a_new_logbook_says_since_when_it_has_been_counting(), test_counts_tokens_of_the_last_24_hours(), test_resting_models_and_when_they_are_back(), test_roles_follow_the_fallback_order_and_unknown_limits_are_allowed(), test_shared_between_processes_through_the_file() (+1 more)

### Community 70 - "Contextualize (small)"
Cohesion: 0.23
Nodes (6): contextualize(), Standalone, ask_json(), ask_text(), contextualize_user(), follow_up_key()

### Community 71 - "How-It-Works (small)"
Cohesion: 0.21
Nodes (8): langgraph + langchain-core (LLM orchestration), Asking back with one-click options, Contextualize step (follow-up rewrite), LangGraph question pipeline, Merge step (join results on shared id), Answerable-question suggestions after failure, Router step (scope, permission, database choice), SQL self-correction retry (max 3 per step)

### Community 72 - "Build Drug Index (small)"
Cohesion: 0.27
Nodes (3): build_index(), main(), test_build_index_counts()

### Community 73 - "State (small)"
Cohesion: 0.22
Nodes (3): next_step(), SqlAttempt, StepResult

### Community 74 - "Rag/Store.Py (small)"
Cohesion: 0.22
Nodes (3): _client(), clinical(), store()

### Community 75 - "Test Config (small)"
Cohesion: 0.29
Nodes (9): make(), test_admin_url_uses_admin_user(), test_api_port_default_and_override(), test_billing_url_uses_ro_user(), test_clinical_url_uses_ro_user(), test_defaults(), test_env_override(), test_password_is_url_encoded() (+1 more)

### Community 76 - "2026-11-18-Plan-5-Production-Habits (small)"
Cohesion: 0.29
Nodes (7): Plan 5 Production Habits: Cache, Paging, Limits, Audit, Metrics, ChatService wrapper (rate limit, cache, semaphore, pages, audit, metrics), Prometheus /metrics counters, Scoped result pages (100 rows, 30 min TTL), Audit log, Conversation memory (session_id), Performance and robustness (pools, timeouts, caps, semaphore, cache)

### Community 77 - "Csv (small)"
Cohesion: 0.36
Nodes (8): SqlRecord, cell(), DB_LABEL, ResultTable(), csvFilename(), downloadCsv(), field(), toCsv()

### Community 78 - "Test Chunking (small)"
Cohesion: 0.33
Nodes (6): chunk_text(), _sentences(), test_chunk_breaks_at_sentence_end(), test_chunk_long_text_overlaps_and_limits(), test_chunk_short_text_single_chunk(), Label chunking (1200 chars, 150 overlap)

### Community 79 - "Brief Features (small)"
Cohesion: 0.22
Nodes (9): Local audit log, Drug-label library (ChromaDB, FDA labels), /health endpoint, /metrics endpoint (Prometheus), Transparency panels (SQL tries, result table, FDA passages, timing bar), Audit Logging, Backend API (POST /query, GET /schema, /health, /metrics), Monitoring & Observability (+1 more)

### Community 80 - "How-It-Works (small)"
Cohesion: 0.27
Nodes (10): fastapi + uvicorn (web API), Thinking orbs (SVG goo animation), Web API (/api/chat, /api/patients, /api/schema), Aether website (black-and-white hairline UI), AETHER_API_PORT shared backend/frontend port, scripts.serve backend launcher (uvicorn app.main:app), index.html SPA entry (dark theme default, mounts /src/main.tsx), Aether website README (+2 more)

### Community 81 - "How-It-Works (small)"
Cohesion: 0.22
Nodes (7): Answer cache (10 min, first questions only), Semantic layer / glossary, Stale Synthea precomputed totals (covered_encounters etc.), run_eval usage (--only, --category), Condition type suffix rule ((disorder) vs (finding)), claims.outstandingp (patient balance owed), Stale-total trap (providers.encounters, payers.covered_encounters)

### Community 82 - "2026-11-17-Plan-3-Drug-Labels-Rag (small)"
Cohesion: 0.29
Nodes (8): Plan 3 Drug Labels RAG + Hybrid Questions, build_drug_index script, Citation label format 'openFDA label: <Drug> — <Section>', DrugLabelStore (ChromaDB wrapper, drug-name matching), rag route (retrieve then synthesize), ChromaDB drug_labels store, Local ONNX embeddings for RAG, openFDA drug label API

### Community 83 - "Glossary (small)"
Cohesion: 0.22
Nodes (8): join_keys, links, patient_hidden_columns, pii_columns, terms, meaning, sql_hint, term

### Community 84 - "Brief Features (small)"
Cohesion: 0.22
Nodes (8): AETHER_API_PORT setting, Secrets in backend/.env (not in git), AI provider config (Groq default, Gemini, Ollama), Rate limit (20 questions/min per address), Connection Pooling & Rate Limiting, Database Connectors (JDBC/ODBC, psycopg2, PyMySQL, pyodbc), OneQuery governed connectors, Secrets & Credentials Management

### Community 85 - "How-It-Works (small)"
Cohesion: 0.28
Nodes (7): chromadb (local vector store), sqlglot (SQL parsing / safety), Clinician view vs patient view, ChromaDB drug_labels collection, Hybrid records + labels questions, RAG answering from drug labels, Manual verification questions Q1-Q12

### Community 86 - "App.Test (small)"
Cohesion: 0.25
Nodes (6): ask(), askChat, box(), getHealth, getPatients, PATIENTS

### Community 87 - "Brief Features (small)"
Cohesion: 0.36
Nodes (7): Aether healthcare chatbot, Billing database (MySQL), Clinical record database (PostgreSQL), Refusal of questions about other patients, Patient view (PostgreSQL RLS with signed identity, MySQL filter rewriting), OAuth / user authentication, Row-Level Security

### Community 88 - "How-It-Works (small)"
Cohesion: 0.29
Nodes (6): prometheus-client (/metrics), CSV export with formula-injection defusing, Paged results with per-user tickets, Prometheus /metrics live counters, Service layer around the pipeline (service.py), Service extras (metrics, audit API, limits in config.py)

### Community 89 - "Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)"
Cohesion: 0.25
Nodes (7): Cross-Database Join, End-to-End Example (sales_db, inventory_db, support_db), FastAPI, Federated Query Engines (Trino/Starburst, Presto, Dremio, Denodo), GitHub multi-db-sql-agent project, Predicate Pushdown, Schema Sidebar

### Community 90 - "How-It-Works (small)"
Cohesion: 0.29
Nodes (3): DB connections with 10s timeout and /health endpoint, setup_databases script (--reset / --rls-only), backend/.env configuration (PG/MySQL admin, GROQ_API_KEY, RO_PASSWORD, RLS_SECRET)

### Community 91 - "How-It-Works (small)"
Cohesion: 0.29
Nodes (6): Backend Python requirements, build_drug_index script, Local embeddings and semantic search (all-MiniLM-L6-v2, 384-dim), openFDA drug labels (DailyMed citations), Trigram typo matching (patient picker, medicine names), Setting up Aether on Windows

### Community 94 - "Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)"
Cohesion: 0.33
Nodes (3): OpenAI GPT Actions SQL middleware pattern, MDB-Link research, Schema Introspection (INFORMATION_SCHEMA)

### Community 96 - "Brief Features (small)"
Cohesion: 0.50
Nodes (4): Aether feature overview, Accuracy report (48-question eval, docs/eval), Governance & Compliance (EU AI Act, HIPAA), Testing & Evaluation (Spider, BIRD, EM/F1)

### Community 97 - "Brief Features (small)"
Cohesion: 0.67
Nodes (4): Live step progress and word-by-word answer streaming, Thinking orbs animation, Frontend Chat UX, Incremental Streaming

### Community 100 - "Building A Multi-Database Chatbot (Structured Data Query + Rag) – 2026 (small)"
Cohesion: 0.67
Nodes (3): Answer cache (10 minutes), Cost Control (LIMIT, timeouts, retries), Query Result Caching

### Community 101 - "2026-11-17-Plan-2-Second-Database-Cross-Db (small)"
Cohesion: 0.67
Nodes (3): Real-MySQL patient isolation attack list, Privacy case scoring (no other patient names or SSNs), Security tests against real DBs

## Ambiguous Edges - Review These
- `Marking fixes (number words, CV02 dual reading)` → `PT01 When was my last visit?`  [AMBIGUOUS]
  docs/eval/2026-11-18-1444-groq-openai_gpt-oss-120b.md · relation: conceptually_related_to

## Knowledge Gaps
- **54 isolated node(s):** `How Aether Works (plain-language guide)`, `DB connections with 10s timeout and /health endpoint`, `openFDA drug labels (DailyMed citations)`, `Thinking orbs (SVG goo animation)`, `Install PostgreSQL 18 (port 5432)` (+49 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 575 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Plan 4 Conversation: Follow-ups, Clarification, Streaming` connect `2026-11-18-Plan-6-Accuracy-Report (small)` to `Conversation Runner & Follow-ups`, `Conversation Memory Store`, `2026-11-18-Plan-5-Production-Habits (small)`, `Web UI Design & Plan`, `2026-11-17-Plan-1-Foundation-Clinical-Chat (small)`, `2026-11-17-Healthcare-Multidb-Chatbot-Design (small)`?**
  _High betweenness centrality (0.151) - this node is a cross-community bridge._
- **Are the 46 inferred relationships involving `Deps` (e.g. with `patients()` and `schema()`) actually correct?**
  _`Deps` has 46 INFERRED edges - model-reasoned connections that need verification._
- **What connects `How Aether Works (plain-language guide)`, `DB connections with 10s timeout and /health endpoint`, `openFDA drug labels (DailyMed citations)` to the rest of the system?**
  _54 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Accuracy Test Harness` be split into smaller, more focused modules?**
  _Cohesion score 0.05212716222533895 - nodes in this community are weakly interconnected._
- **Why does `UI Web Front End Implementation Plan` connect `Web UI Design & Plan` to `2026-11-18-Plan-6-Accuracy-Report (small)`, `Frontend API Types & Conversation`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `run_chat()` (e.g. with `get_runner()` and `Deps`) actually correct?**
  _`run_chat()` has 2 INFERRED edges - model-reasoned connections that need verification._

### Low-confidence Hints
_AMBIGUOUS edges — the extractor was unsure. Verify before acting on these._

- **What is the exact relationship between `Marking fixes (number words, CV02 dual reading)` and `PT01 When was my last visit?`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._