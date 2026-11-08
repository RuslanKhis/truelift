"""An independent reference for the golden cases: plain-Python d-separation, no networkx.

This is not the product's identification (G06 writes that in ``truelift.causal.identify``). It
exists so the golden expectations are checked by a second, small, readable implementation of the
same rules: if Thao's expectation and this oracle disagree, one of them is wrong, and G06 is not
built against a mistake. It reads the thresholds, proxies, normalisation and CATE rules from the
real rule files.

d-separation uses the moral ancestral graph (Lauritzen et al. 1990): X and Y are d-separated by
Z in a DAG exactly when they are disconnected in the moralised graph of An(X, Y, Z) once Z is
removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations

from tests.golden.cases import GoldenCase
from truelift.causal.rules import RuleSet

FORBIDDEN_PREFIXES = ("truth_",)  # G06's forbidden.py adds the private prefix (C4).
CONTROL_ROLES = ("confounder", "predictor", "modifier")


def is_forbidden(column: str) -> bool:
    return column.lower().startswith(FORBIDDEN_PREFIXES)


# --- graph helpers ------------------------------------------------------------------------


def _children(edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for a, b in edges:
        out.setdefault(a, set()).add(b)
    return out


def _parents(edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for a, b in edges:
        out.setdefault(b, set()).add(a)
    return out


def descendants(edges: list[tuple[str, str]], node: str) -> set[str]:
    kids, seen, stack = _children(edges), set(), [node]
    while stack:
        for k in kids.get(stack.pop(), ()):
            if k not in seen:
                seen.add(k)
                stack.append(k)
    return seen


def ancestors(edges: list[tuple[str, str]], nodes: set[str]) -> set[str]:
    """``nodes`` and everything with a directed path into them."""
    pars, seen, stack = _parents(edges), set(nodes), list(nodes)
    while stack:
        for p in pars.get(stack.pop(), ()):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return seen


def d_separated(edges: list[tuple[str, str]], x: str, y: str, z: set[str]) -> bool:
    keep = ancestors(edges, {x, y} | z)
    sub = [(a, b) for a, b in edges if a in keep and b in keep]
    adj: dict[str, set[str]] = {n: set() for n in keep}
    for a, b in sub:
        adj[a].add(b)
        adj[b].add(a)
    for ps in _parents(sub).values():
        for p, q in combinations(sorted(ps), 2):
            adj[p].add(q)
            adj[q].add(p)
    seen, stack = {x}, [x]
    while stack:
        for n in adj[stack.pop()]:
            if n == y:
                return False
            if n not in seen and n not in z:
                seen.add(n)
                stack.append(n)
    return True


def open_backdoor_paths(edges: list[tuple[str, str]], t: str, y: str, z: set[str]) -> list[list[str]]:
    """Every simple path from t to y that starts with an arrow into t and is open given z."""
    bd = [(a, b) for a, b in edges if a != t]
    directed = set(bd)
    nbrs: dict[str, set[str]] = {}
    for a, b in bd:
        nbrs.setdefault(a, set()).add(b)
        nbrs.setdefault(b, set()).add(a)
    out: list[list[str]] = []

    def is_open(path: list[str]) -> bool:
        for i in range(1, len(path) - 1):
            prev, node, nxt = path[i - 1], path[i], path[i + 1]
            collider = (prev, node) in directed and (nxt, node) in directed
            if collider:
                if not ({node} | descendants(bd, node)) & z:
                    return False
            elif node in z:
                return False
        return True

    def walk(path: list[str]) -> None:
        for n in sorted(nbrs.get(path[-1], ())):
            if n in path:
                continue
            if n == y:
                if is_open(path + [n]):
                    out.append(path + [n])
                continue
            walk(path + [n])

    for p in sorted(nbrs.get(t, ())):
        if (p, t) in directed:
            walk([t, p])
    return out


# --- the reference analysis ---------------------------------------------------------------


@dataclass
class Analysis:
    decision: str
    blocks: list[dict] = field(default_factory=list)
    adjustment_set: list[str] | None = None
    x_cols: list[str] | None = None
    fixed_effects: list[str] | None = None
    cate_covariates: list[str] | None = None
    cate_degree: int | None = None
    warnings: list[dict] | None = None
    compile: dict | None = None
    no_valid_set_exists: bool | None = None


def analyse(case: GoldenCase, rules: RuleSet) -> Analysis:
    dag, mapping, data = case.dag, case.mapping, case.data
    t, y = dag.treatment, dag.outcome
    edges = [tuple(e) for e in dag.edges]
    after_t = descendants(edges, t)
    blocks: list[dict] = []
    warnings: list[dict] = []

    # Which nodes have usable data: their own column (not ground truth) or an accepted proxy.
    data_col: dict[str, str] = {}
    for n in dag.nodes:
        if n.id in (t, y):
            continue
        if n.column:
            if is_forbidden(n.column):
                warnings.append({"code": "forbidden_excluded", "subjects": [n.column]})
            else:
                data_col[n.id] = n.column
        elif n.proxy:
            rule = rules.proxies.by_id(n.proxy.rule)
            assert n.id in rule.stands_for, f"{case.id}: proxy {rule.id} cannot stand in for {n.id}"
            assert mapping.column(n.proxy.column).type in rule.semantic_types
            data_col[n.id] = n.proxy.column

    # C3 a: something the discount causes is labelled as a control or an effect modifier.
    for n in dag.nodes:
        if n.id in after_t and (n.role in CONTROL_ROLES or n.id in dag.modifiers):
            blocks.append({"code": "descendant_in_controls", "node_ids": [n.id], "remedies": []})

    # C3 b: the ancestral adjustment set (rules/identification.yaml, adjustment.rule).
    relevant = ancestors(edges, {t, y}) - after_t - {t, y}
    z = {n for n in relevant if n in data_col}
    accepted = set(dag.risk_accepted)
    bd = [(a, b) for a, b in edges if a != t]
    valid = d_separated(bd, t, y, z | accepted)
    no_valid = None
    if not valid:
        missing = set()
        for path in open_backdoor_paths(edges, t, y, z | accepted):
            missing |= {n for n in path[1:-1] if n not in data_col and n not in accepted}
        assert missing, f"{case.id}: an open back-door path with no unobserved node"
        for node in sorted(missing):
            remedies = ["add_data", "accept_risk"]
            if rules.proxies.for_node(node):
                remedies = ["add_data", "use_proxy", "accept_risk"]
            blocks.append({"code": "unobserved_confounder", "node_ids": [node], "remedies": remedies})
        # Completeness: no other set built from the available data would have done better.
        allowed = sorted(n for n in data_col if n not in after_t)
        no_valid = not any(
            d_separated(bd, t, y, set(s) | accepted)
            for k in range(len(allowed) + 1)
            for s in combinations(allowed, k)
        )

    # C3 c, d: panel size and treatment variation.
    th = rules.identification.threshold
    checks = [
        ("too_few_weeks", data.weeks < th("min_weeks")),
        ("too_few_regions", data.regions < th("min_regions")),
        ("too_few_rows", data.rows < th("min_rows")),
        ("too_few_treated_rows", data.treated_share < th("min_treated_share")),
        ("too_few_untreated_rows", data.untreated_share < th("min_untreated_share")),
        ("too_few_treatment_levels", data.treatment_levels < th("min_treatment_levels")),
        ("panel_gaps", data.gap_share > th("max_gap_share")),
    ]
    blocks += [{"code": code, "node_ids": [], "remedies": ["add_data"]} for code, failed in checks if failed]
    blocks.sort(key=lambda b: (b["code"], b["node_ids"]))

    if blocks:
        return Analysis("blocked", blocks=blocks, no_valid_set_exists=no_valid)

    adjustment = sorted(z)
    x_cols = sorted(data_col[n] for n in adjustment)
    fixed = sorted(c.name for c in mapping.columns if c.role in ("region", "category"))

    if data.regions < rules.identification.warnings["few_regions"].below:
        warnings.append({"code": "few_regions", "subjects": []})
    proxied = sorted(n.id for n in dag.nodes if n.proxy and n.id in z)
    if proxied:
        warnings.append({"code": "proxy_used", "subjects": proxied})
    if accepted:
        warnings.append({"code": "risk_accepted", "subjects": sorted(accepted)})
    left_out = sorted(
        n.id
        for n in dag.nodes
        if n.role in CONTROL_ROLES and n.id in data_col and n.id not in z and n.id not in after_t
    )
    if left_out:
        warnings.append({"code": "left_out", "subjects": left_out})

    # CATE covariates (rules/cate.yaml).
    eligible = sorted(data_col[m] for m in dag.modifiers if m in data_col and m not in after_t)
    cap = int(rules.cate.covariates.max_count.value)
    cate, dropped = eligible[:cap], eligible[cap:]
    if dropped:
        warnings.append({"code": "cate_capped", "subjects": dropped})
    degree = None
    if cate:
        degree = rules.cate.degree_for(data.rows)
        if data.rows < rules.cate.structure.degree.small_sample_rows:
            warnings.append({"code": "cate_small_sample", "subjects": []})
    warnings.sort(key=lambda w: (w["code"], w["subjects"]))

    return Analysis(
        "identified",
        adjustment_set=adjustment,
        x_cols=x_cols,
        fixed_effects=fixed,
        cate_covariates=cate,
        cate_degree=degree,
        warnings=warnings,
        compile=_compile(case, rules, x_cols, cate),
    )


def _compile(case: GoldenCase, rules: RuleSet, x_cols: list[str], cate: list[str]) -> dict:
    """The C2 settings the golden cases pin: treatment kind, spend, threshold and scalers."""
    mapping = case.mapping
    t_col = mapping.column(case.dag.node(case.dag.treatment).column)
    y_col = case.dag.node(case.dag.outcome).column
    spend = mapping.by_role("treatment_spend")
    if t_col.role == "treatment_rate":
        assert t_col.type == "rate" and t_col.bounded_0_1, f"{case.id}: a rate treatment lies in [0, 1]"
        if not spend:
            return {"error": "missing_spend_column"}
        kind, spend_col, sales_col = "percentage", spend[0].name, y_col
    else:
        assert t_col.role == "treatment_spend", f"{case.id}: the treatment column is a rate or a spend"
        kind, spend_col, sales_col = "spend", t_col.name, None
    has_population = bool(mapping.by_role("population"))
    scalers: dict[str, list[str]] = {"median_normalize_cols": [], "population_median_normalize_cols": []}
    for name in sorted(set(x_cols) | set(cate)):
        col = mapping.column(name)
        scaler = rules.normalisation.scaler_for(
            col.type, has_population=has_population, bounded_0_1=col.bounded_0_1
        )
        assert scaler != "not_a_feature", f"{case.id}: {name} cannot be a control"
        if scaler != "none":
            scalers[scaler].append(name)
    return {
        "treatment_types": {t_col.name: kind},
        "sales_col": sales_col,
        "treatment_spend_cols": {t_col.name: spend_col},
        "opt_threshold_roi": round(1 / case.margin, 6) if case.margin else 1.0,
        "scalers": scalers,
        "error": None,
    }
