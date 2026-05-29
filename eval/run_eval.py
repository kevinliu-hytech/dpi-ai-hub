"""
Eval Runner — Tests the hub pipeline against predefined cases.
Usage: python eval/run_eval.py [--case CASE_ID] [--verbose]

Runs directly against the agents (no HTTP auth needed).
Deploy to EC2 and run: cd /home/ec2-user/gbis-analysis && python eval/run_eval.py
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hub_router import HubRouter
from chat_engine import ChatEngine
from external_data_agent import ExternalDataAgent

router = None
internal_agent = None
external_agent = None


def init_agents():
    global router, internal_agent, external_agent
    print("Loading agents...")
    router = HubRouter()
    internal_agent = ChatEngine()
    external_agent = ExternalDataAgent()
    print("Agents ready.\n")


def call_hub(question, history=None):
    """Route + call the appropriate agent."""
    route_result = router.route(question)
    agent_name = route_result.get('agent', 'internal_data')

    if agent_name == 'external_data':
        response = external_agent.chat(question, history or None)
        response['agent'] = 'external'
    else:
        response = internal_agent.chat(question, history or None)
        response['agent'] = 'internal'

    return response


def load_cases(case_id=None):
    path = os.path.join(os.path.dirname(__file__), 'eval_cases.json')
    with open(path) as f:
        cases = json.load(f)
    if case_id:
        cases = [c for c in cases if c['id'] == case_id]
    return cases


def check_route(result, expected):
    actual = result.get('agent', '')
    if actual == expected:
        return True, f"route={actual}"
    return False, f"route={actual} (expected {expected})"


def check_sql_contains(result, keywords):
    sql = result.get('sql', '') or ''
    if isinstance(sql, list):
        sql = ' '.join(sql)
    sql_lower = sql.lower()
    failures = []
    for kw in keywords:
        if kw.lower() not in sql_lower:
            failures.append(kw)
    if failures:
        return False, f"SQL missing: {failures}"
    return True, "SQL contains all expected keywords"


def check_sql_not_contains(result, keywords):
    sql = result.get('sql', '') or ''
    if isinstance(sql, list):
        sql = ' '.join(sql)
    sql_lower = sql.lower()
    failures = []
    for kw in keywords:
        if kw.lower() in sql_lower:
            failures.append(kw)
    if failures:
        return False, f"SQL should NOT contain: {failures}"
    return True, "SQL correctly excludes keywords"


def check_answer_contains(result, keywords, any_mode=False):
    answer = (result.get('answer', '') or '').lower()
    if any_mode:
        for kw in keywords:
            if kw.lower() in answer:
                return True, f"Answer contains '{kw}'"
        return False, f"Answer missing ALL of: {keywords}"
    failures = []
    for kw in keywords:
        if kw.lower() not in answer:
            failures.append(kw)
    if failures:
        return False, f"Answer missing: {failures}"
    return True, "Answer contains all expected keywords"


def check_answer_not_contains(result, keywords):
    answer = (result.get('answer', '') or '').lower()
    failures = []
    for kw in keywords:
        if kw.lower() in answer:
            failures.append(kw)
    if failures:
        return False, f"Answer should NOT contain: {failures}"
    return True, "Answer correctly excludes keywords"


def check_data(result, data_check):
    data = result.get('data')
    if not data:
        if data_check.get('min_rows', 0) > 0:
            return False, f"No data returned (expected min {data_check['min_rows']} rows)"
        return True, "No data (as expected)"
    if 'min_rows' in data_check and len(data) < data_check['min_rows']:
        return False, f"Only {len(data)} rows (expected min {data_check['min_rows']})"
    return True, f"{len(data)} rows returned"


def check_chart(result, chart_check):
    chart = result.get('chart')
    expected_show = chart_check.get('show')

    if expected_show is False:
        if chart is None or chart == []:
            return True, "No chart (as expected)"
        return False, f"Chart shown but expected none: {json.dumps(chart)[:100]}"

    if expected_show is True:
        if not chart:
            return False, "No chart but expected one"
        cfg = chart[0] if isinstance(chart, list) else chart
        failures = []

        if 'type' in chart_check and cfg.get('type') != chart_check['type']:
            failures.append(f"type={cfg.get('type')} (expected {chart_check['type']})")

        if 'x_contains' in chart_check:
            x = (cfg.get('x') or '').lower()
            if chart_check['x_contains'].lower() not in x:
                failures.append(f"x={cfg.get('x')} (expected contains '{chart_check['x_contains']}')")

        if 'y_not_contains' in chart_check:
            y = (cfg.get('y') or '').lower()
            if chart_check['y_not_contains'].lower() in y:
                failures.append(f"y={cfg.get('y')} (should NOT contain '{chart_check['y_not_contains']}')")

        if failures:
            return False, "; ".join(failures)
        return True, f"Chart OK: type={cfg.get('type')}, x={cfg.get('x')}, y={cfg.get('y')}"

    return True, "No chart check"


def run_case(case, verbose=False):
    question = case['question']
    history = case.get('history', [])
    checks = case['checks']
    results_list = []

    response = call_hub(question, history if history else None)

    if 'error' in response and not response.get('answer'):
        print(f"  ERROR: {response.get('error')}")
        return [('agent', False, str(response.get('error')))]

    agent_name = response.get('agent', 'unknown')

    if verbose:
        print(f"  Route: {agent_name}")
        print(f"  Answer: {(response.get('answer') or '')[:120]}...")
        if response.get('sql'):
            sql_display = response['sql'] if isinstance(response['sql'], str) else response['sql'][0] if response['sql'] else ''
            print(f"  SQL: {str(sql_display)[:150]}...")
        if response.get('chart'):
            print(f"  Chart: {json.dumps(response['chart'])[:100]}")

    # Check route
    if 'route' in checks:
        passed, msg = check_route({'agent': agent_name}, checks['route'])
        results_list.append(('route', passed, msg))

    # Check SQL
    if 'sql_contains' in checks:
        passed, msg = check_sql_contains(response, checks['sql_contains'])
        results_list.append(('sql_contains', passed, msg))

    if 'sql_not_contains' in checks:
        passed, msg = check_sql_not_contains(response, checks['sql_not_contains'])
        results_list.append(('sql_not_contains', passed, msg))

    # Check data
    if 'data_check' in checks:
        passed, msg = check_data(response, checks['data_check'])
        results_list.append(('data', passed, msg))

    # Check chart
    if 'chart' in checks:
        passed, msg = check_chart(response, checks['chart'])
        results_list.append(('chart', passed, msg))

    # Check answer
    if 'answer_contains' in checks:
        any_mode = checks.get('answer_contains_any', False)
        passed, msg = check_answer_contains(response, checks['answer_contains'], any_mode)
        results_list.append(('answer_contains', passed, msg))

    if 'answer_not_contains' in checks:
        passed, msg = check_answer_not_contains(response, checks['answer_not_contains'])
        results_list.append(('answer_not_contains', passed, msg))

    # Check value_range
    if 'value_range' in checks:
        vr = checks['value_range']
        if 'answer_not_contains' in vr:
            passed, msg = check_answer_not_contains(response, vr['answer_not_contains'])
            results_list.append(('value_range', passed, msg))

    return results_list


def main():
    parser = argparse.ArgumentParser(description='Run eval cases')
    parser.add_argument('--case', type=str, help='Run specific case ID only')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    args = parser.parse_args()

    cases = load_cases(args.case)
    if not cases:
        print("No cases found.")
        return

    init_agents()
    print(f"Running {len(cases)} eval cases...\n")

    total_checks = 0
    passed_checks = 0
    failed_cases = []

    for case in cases:
        print(f"{'─' * 60}")
        print(f"[{case['id']}] {case['description']}")
        print(f"  Q: {case['question']}")
        if case.get('history'):
            print(f"  (with {len(case['history'])} history messages)")

        try:
            results = run_case(case, args.verbose)
        except Exception as e:
            print(f"  ERROR: {e}")
            failed_cases.append(case['id'])
            continue

        case_passed = True
        for check_name, passed, msg in results:
            total_checks += 1
            if passed:
                passed_checks += 1
            else:
                case_passed = False
            print(f"  {'PASS' if passed else 'FAIL'} {check_name}: {msg}")

        if not case_passed:
            failed_cases.append(case['id'])

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {passed_checks}/{total_checks} checks passed ({100*passed_checks//max(total_checks,1)}%)")
    if failed_cases:
        print(f"FAILED CASES ({len(failed_cases)}): {', '.join(failed_cases)}")
    else:
        print("ALL CASES PASSED!")


if __name__ == '__main__':
    main()
