from auth.usage_limiter import check_budget, record_usage, set_token_plan, get_token_plan

print(get_token_plan('TEST_HOSP_001'))
print(set_token_plan('TEST_HOSP_001', 'day', 100))
print(get_token_plan('TEST_HOSP_001'))
print(check_budget('TEST_HOSP_001'))
print(record_usage('TEST_HOSP_001', 30))
print(record_usage('TEST_HOSP_001', 40))
print(record_usage('TEST_HOSP_001', 50))
print(check_budget('TEST_HOSP_001'))