"""Pure curve-fitting engine for the CNLS "CF option" feature.

Fits a single parameter's values (y) against per-file x index (x) using a
selected method, and provides a 95% confidence band for the fitted curve.

Methods are grouped into CATEGORIES for the GUI dropdown. Polynomial is handled
by linear least squares (with an exact prediction band); every other model is a
nonlinear least-squares fit (scipy.curve_fit) whose confidence band comes from
the parameter covariance via a numerical Jacobian — so the band machinery is the
same for all nonlinear models.

This module has no Dear PyGui dependency so it can be unit-tested directly.
"""
import numpy as np

try:
    from scipy.optimize import curve_fit
    from scipy.stats import t as _student_t
    _HAS_SCIPY = True
except Exception:  # pragma: no cover - scipy expected in project env
    _HAS_SCIPY = False

# Default confidence level for the band (fit-curve confidence interval).  The
# level is saved with every fit so different parameters can use different CIs.
DEFAULT_CONF_LEVEL = 0.95


def _confidence_level(value, default=None):
    """Return a valid fractional CI, or *default* when the value is invalid."""
    try:
        level = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(level) or not 0.50 <= level <= 0.9999:
        return default
    return level


def _t_value(dof, confidence_level=DEFAULT_CONF_LEVEL):
    """Two-sided t multiplier for a fractional confidence level."""
    if dof is None or dof <= 0:
        return float("nan")
    confidence_level = _confidence_level(confidence_level)
    if confidence_level is None:
        return float("nan")
    if _HAS_SCIPY:
        return float(_student_t.ppf(0.5 + confidence_level / 2.0, dof))
    return 1.96


# ── Model functions ───────────────────────────────────────────────────────────
def _model_exp(x, a, b, c):        return a * np.exp(b * x) + c
def _model_exp2(x, a, b):          return a * np.exp(b * x)
def _model_asymp(x, a, b, c):      return a - (a - c) * np.exp(-b * x)
def _model_power(x, a, b):         return a * np.power(x, b)
def _model_log(x, a, b):           return a * np.log(x) + b
def _model_log3(x, a, b, c):       return a / (1.0 + np.exp(-b * (x - c)))
def _model_log4(x, a, b, c, d):    return d + (a - d) / (1.0 + np.power(x / c, b))
def _model_log5(x, a, b, c, d, g): return d + (a - d) / np.power(1.0 + np.power(x / c, b), g)
def _model_gompertz(x, a, b, c):   return a * np.exp(-b * np.exp(-c * x))
def _model_weibull(x, a, b, c, k): return a - b * np.exp(-c * np.power(x, k))
def _model_hill(x, a, k, n):       return a * np.power(x, n) / (np.power(k, n) + np.power(x, n))
def _model_boltz(x, a1, a2, x0, dx): return a2 + (a1 - a2) / (1.0 + np.exp((x - x0) / dx))
def _model_mm(x, vmax, km):        return vmax * x / (km + x)
def _model_gauss(x, a, b, c, d):   return d + a * np.exp(-((x - b) ** 2) / (2.0 * c * c))
def _model_rational(x, a, b, c):   return (a + b * x) / (1.0 + c * x)
def _model_sine(x, a, b, c, d):    return a * np.sin(b * x + c) + d


# name -> (kind, model fn, n params, positivity requirement)
#   req: None (any x), "positive" (x > 0), "nonneg" (x >= 0)
_MODELS = {
    "Exponential":       ("exp",      _model_exp,      3, None),
    "Exponential 2P":    ("exp2",     _model_exp2,     2, None),
    "Asymptotic":        ("asymp",    _model_asymp,    3, None),
    "Power":             ("power",    _model_power,    2, "positive"),
    "Logarithmic":       ("log",      _model_log,      2, "positive"),
    "Logistic 3P":       ("log3",     _model_log3,     3, None),
    "Logistic 4P":       ("log4",     _model_log4,     4, "positive"),
    "Logistic 5P":       ("log5",     _model_log5,     5, "positive"),
    "Gompertz":          ("gompertz", _model_gompertz, 3, None),
    "Weibull":           ("weibull",  _model_weibull,  4, "nonneg"),
    "Hill":              ("hill",     _model_hill,     3, "nonneg"),
    "Boltzmann":         ("boltz",    _model_boltz,    4, None),
    "Michaelis-Menten":  ("mm",       _model_mm,       2, "nonneg"),
    "Gaussian":          ("gauss",    _model_gauss,    4, None),
    "Hyperbola":         ("rational", _model_rational, 3, None),
    "Sine":              ("sine",     _model_sine,     4, None),
}
_MODEL_BY_KIND = {spec[0]: spec[1] for spec in _MODELS.values()}

# Ordered classification used to build the GUI dropdown (category -> methods).
CATEGORIES = {
    "Polynomial": ["Polynomial"],
    "Exponential": ["Exponential", "Exponential 2P", "Asymptotic"],
    "Power / Log": ["Power", "Logarithmic"],
    "Sigmoidal": ["Logistic 3P", "Logistic 4P", "Logistic 5P", "Gompertz",
                  "Weibull", "Hill", "Boltzmann", "Michaelis-Menten"],
    "Peak": ["Gaussian"],
    "Rational": ["Hyperbola"],
    "Periodic": ["Sine"],
}

# Flat list of every method (Polynomial first, then registry order).
METHODS = [m for methods in CATEGORIES.values() for m in methods]


def category_of(method):
    """Return the category name that contains method (default 'Polynomial')."""
    for category, methods in CATEGORIES.items():
        if method in methods:
            return category
    return "Polynomial"


# Symbolic reference formula shown once a method is selected. Uses '×' for
# multiplication (U+00D7 is in the font's Latin-1 range) and plain ASCII for the
# rest so it renders with the GUI font (no minus/sub/superscript glyphs).
FORMULAS = {
    "Polynomial":       "y = a_n×x^n + ... + a_1×x + a_0",
    "Exponential":      "y = a×e^(b×x) + c",
    "Exponential 2P":   "y = a×e^(b×x)",
    "Asymptotic":       "y = a - (a-c)×e^(-b×x)",
    "Power":            "y = a×x^b",
    "Logarithmic":      "y = a×ln(x) + b",
    "Logistic 3P":      "y = a / (1 + e^(-b×(x-c)))",
    "Logistic 4P":      "y = d + (a-d) / (1 + (x/c)^b)",
    "Logistic 5P":      "y = d + (a-d) / (1 + (x/c)^b)^g",
    "Gompertz":         "y = a×e^(-b×e^(-c×x))",
    "Weibull":          "y = a - b×e^(-c×x^k)",
    "Hill":             "y = a×x^n / (k^n + x^n)",
    "Boltzmann":        "y = a2 + (a1-a2) / (1 + e^((x-x0)/dx))",
    "Michaelis-Menten": "y = Vmax×x / (Km + x)",
    "Gaussian":         "y = d + a×e^(-(x-b)^2 / (2×c^2))",
    "Hyperbola":        "y = (a + b×x) / (1 + c×x)",
    "Sine":             "y = a×sin(b×x + c) + d",
}


def formula_of(method):
    """Symbolic reference formula for a method ('' if unknown)."""
    return FORMULAS.get(method, "")


def _fmt(v):
    return f"{v:.3g}"


def _clean_signs(s):
    """Turn '+ -3' into '- 3' for readable equations."""
    return s.replace("+ -", "- ")


def _eq_raw(fit):
    if not fit.get("ok"):
        return fit.get("message", "")
    m = fit["method"]
    a = fit["coeffs"]
    try:
        if m == "Polynomial":
            deg = fit.get("degree", len(a) - 1)
            terms = []
            for i, co in enumerate(a):
                power = deg - i
                if power == 0:
                    terms.append(_fmt(co))
                elif power == 1:
                    terms.append(f"{_fmt(co)}×x")
                else:
                    terms.append(f"{_fmt(co)}×x^{power}")
            return "y = " + " + ".join(terms)
        if m == "Exponential":       return f"y = {_fmt(a[0])}×e^({_fmt(a[1])}×x) + {_fmt(a[2])}"
        if m == "Exponential 2P":    return f"y = {_fmt(a[0])}×e^({_fmt(a[1])}×x)"
        if m == "Asymptotic":        return f"y = {_fmt(a[0])} - ({_fmt(a[0])}-{_fmt(a[2])})×e^(-{_fmt(a[1])}×x)"
        if m == "Power":             return f"y = {_fmt(a[0])}×x^{_fmt(a[1])}"
        if m == "Logarithmic":       return f"y = {_fmt(a[0])}×ln(x) + {_fmt(a[1])}"
        if m == "Logistic 3P":       return f"y = {_fmt(a[0])} / (1 + e^(-{_fmt(a[1])}×(x-{_fmt(a[2])})))"
        if m == "Logistic 4P":       return f"y = {_fmt(a[3])} + ({_fmt(a[0])}-{_fmt(a[3])}) / (1 + (x/{_fmt(a[2])})^{_fmt(a[1])})"
        if m == "Logistic 5P":       return f"y = {_fmt(a[3])} + ({_fmt(a[0])}-{_fmt(a[3])}) / (1 + (x/{_fmt(a[2])})^{_fmt(a[1])})^{_fmt(a[4])}"
        if m == "Gompertz":          return f"y = {_fmt(a[0])}×e^(-{_fmt(a[1])}×e^(-{_fmt(a[2])}×x))"
        if m == "Weibull":           return f"y = {_fmt(a[0])} - {_fmt(a[1])}×e^(-{_fmt(a[2])}×x^{_fmt(a[3])})"
        if m == "Hill":              return f"y = {_fmt(a[0])}×x^{_fmt(a[2])} / ({_fmt(a[1])}^{_fmt(a[2])} + x^{_fmt(a[2])})"
        if m == "Boltzmann":         return f"y = {_fmt(a[1])} + ({_fmt(a[0])}-{_fmt(a[1])}) / (1 + e^((x-{_fmt(a[2])})/{_fmt(a[3])}))"
        if m == "Michaelis-Menten":  return f"y = {_fmt(a[0])}×x / ({_fmt(a[1])} + x)"
        if m == "Gaussian":          return f"y = {_fmt(a[3])} + {_fmt(a[0])}×e^(-(x-{_fmt(a[1])})^2 / (2×{_fmt(a[2])}^2))"
        if m == "Hyperbola":         return f"y = ({_fmt(a[0])} + {_fmt(a[1])}×x) / (1 + {_fmt(a[2])}×x)"
        if m == "Sine":              return f"y = {_fmt(a[0])}×sin({_fmt(a[1])}×x + {_fmt(a[2])}) + {_fmt(a[3])}"
    except Exception:
        pass
    return "y = " + ", ".join(_fmt(v) for v in a)


def equation_string(fit):
    """Fitted equation with numeric coefficients substituted (message if not ok)."""
    return _clean_signs(_eq_raw(fit))


def _clean_xy(x, y):
    x = np.asarray(x, dtype=np.float64).reshape(-1)
    y = np.asarray(y, dtype=np.float64).reshape(-1)
    n = min(len(x), len(y))
    x, y = x[:n], y[:n]
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask]


def _r_squared(y, yhat):
    tss = float(np.sum((y - np.mean(y)) ** 2))
    rss = float(np.sum((y - yhat) ** 2))
    if tss <= 0:
        return 1.0 if rss <= 1e-30 else 0.0
    return 1.0 - rss / tss


def _fail(method, message, confidence_level=DEFAULT_CONF_LEVEL):
    return {"ok": False, "method": method, "message": message,
            "r2": float("nan"), "coeffs": (),
            "confidence_level": confidence_level}


def fit_parameter(x, y, method, degree=1, confidence_level=DEFAULT_CONF_LEVEL):
    """Fit y vs x with the given method.

    Returns a result dict. Keys always present: ok, method, message, r2, coeffs.
    When ok, additional private keys support evaluate(): _kind and model state.
    """
    confidence_level = _confidence_level(confidence_level)
    if confidence_level is None:
        return _fail(method, "confidence level must be between 50% and 99.99%", None)

    x, y = _clean_xy(x, y)
    n = len(x)

    if method == "Polynomial":
        return _fit_polynomial(x, y, int(degree), n, confidence_level)

    if method not in _MODELS:
        return _fail(method, f"unknown method '{method}'", confidence_level)

    if not _HAS_SCIPY:
        return _fail(method, "scipy not available for nonlinear fit", confidence_level)

    kind, model, p, req = _MODELS[method]
    if req == "positive" and np.any(x <= 0):
        return _fail(method, "x must be > 0 for this method", confidence_level)
    if req == "nonneg" and np.any(x < 0):
        return _fail(method, "x must be >= 0 for this method", confidence_level)
    if n < p + 1:
        return _fail(method, f"need >= {p + 1} points for {method}", confidence_level)

    p0 = _initial_guess(kind, x, y)
    try:
        with np.errstate(all="ignore"):
            popt, pcov = curve_fit(model, x, y, p0=p0, maxfev=20000)
            yhat = model(x, *popt)
    except Exception as exc:
        return _fail(method, f"fit did not converge ({type(exc).__name__})", confidence_level)
    if not np.all(np.isfinite(yhat)):
        return _fail(method, "fit produced non-finite values", confidence_level)

    return {"ok": True, "method": method, "message": "",
            "r2": _r_squared(y, yhat), "coeffs": tuple(float(c) for c in popt),
            "confidence_level": confidence_level,
            "_kind": kind, "_popt": np.asarray(popt, float),
            "_pcov": np.asarray(pcov, float), "_dof": n - p}


def _fit_polynomial(x, y, degree, n, confidence_level):
    p = degree + 1
    if n < p + 1:
        return _fail("Polynomial", f"need >= {p + 1} points for degree {degree}", confidence_level)
    try:
        X = np.vander(x, p)  # columns high -> low power
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        yhat = X @ beta
        dof = n - p
        rss = float(np.sum((y - yhat) ** 2))
        sigma2 = rss / dof if dof > 0 else float("nan")
        cov = sigma2 * np.linalg.inv(X.T @ X)
    except np.linalg.LinAlgError:
        return _fail("Polynomial", "singular fit (check x spread / degree)", confidence_level)
    return {"ok": True, "method": "Polynomial", "message": "", "degree": degree,
            "r2": _r_squared(y, yhat), "coeffs": tuple(float(c) for c in beta),
            "confidence_level": confidence_level,
            "_kind": "poly", "_beta": beta, "_cov": cov, "_dof": dof}


def _initial_guess(kind, x, y):
    """Heuristic starting parameters for each nonlinear model."""
    n = len(x)
    ymin, ymax, ymean = float(np.min(y)), float(np.max(y)), float(np.mean(y))
    xmin, xmax, xmean = float(np.min(x)), float(np.max(x)), float(np.mean(x))
    xspan = (xmax - xmin) or 1.0
    yspan = (ymax - ymin) or 1.0
    slope = float(np.polyfit(x, y, 1)[0]) if n >= 2 else 0.0
    sign = 1.0 if slope >= 0 else -1.0
    xmed = max(float(np.median(x)), 1e-6)
    x_at_ymax = float(x[int(np.argmax(y))])
    y_at_xmin = float(y[int(np.argmin(x))])
    y_at_xmax = float(y[int(np.argmax(x))])

    if kind == "exp":
        return [yspan, 0.1 * sign, ymin]
    if kind == "exp2":
        if np.all(y > 0):
            b0, loga = np.polyfit(x, np.log(y), 1)
            return [float(np.exp(loga)), float(b0)]
        return [ymean or 1.0, 0.1 * sign]
    if kind == "asymp":
        return [ymax, 1.0 / xspan, y_at_xmin]
    if kind == "power":
        if np.all(y > 0):
            b0, loga = np.polyfit(np.log(x), np.log(y), 1)
            return [float(np.exp(loga)), float(b0)]
        return [1.0, 1.0]
    if kind == "log":
        a0, b0 = np.polyfit(np.log(x), y, 1)
        return [float(a0), float(b0)]
    if kind == "log3":
        return [ymax + 0.05 * yspan, sign * 4.0 / xspan, xmean]
    if kind == "log4":
        return [y_at_xmin, 1.0, xmed, y_at_xmax]
    if kind == "log5":
        return [y_at_xmin, 1.0, xmed, y_at_xmax, 1.0]
    if kind == "gompertz":
        return [ymax + 0.05 * yspan, 1.0, 1.0 / xspan]
    if kind == "weibull":
        return [ymax, yspan, 1.0 / xspan, 1.0]
    if kind == "hill":
        return [ymax, xmed, 1.0]
    if kind == "boltz":
        return [y_at_xmin, y_at_xmax, xmean, xspan / 4.0]
    if kind == "mm":
        return [ymax + 0.1 * yspan, xmed]
    if kind == "gauss":
        return [yspan, x_at_ymax, xspan / 4.0, ymin]
    if kind == "rational":
        return [y_at_xmin, slope, 0.0]
    if kind == "sine":
        return [yspan / 2.0, 2.0 * np.pi / xspan, 0.0, ymean]
    return None


def evaluate(result, x_new):
    """Return (yhat, y_lower, y_upper) arrays for x_new using a fit result.

    y_lower/y_upper are the fit result's confidence band. For a non-ok result,
    returns arrays of NaN.  Older result dictionaries default to 95%.
    """
    x_new = np.asarray(x_new, dtype=np.float64).reshape(-1)
    if not result.get("ok"):
        nan = np.full_like(x_new, np.nan)
        return nan, nan.copy(), nan.copy()

    dof = result["_dof"]
    t = _t_value(dof, result.get("confidence_level", DEFAULT_CONF_LEVEL))

    with np.errstate(all="ignore"):
        if result["_kind"] == "poly":
            beta = result["_beta"]
            cov = result["_cov"]
            X0 = np.vander(x_new, len(beta))
            yhat = X0 @ beta
            var = np.sum((X0 @ cov) * X0, axis=1)
        else:
            model = _MODEL_BY_KIND[result["_kind"]]
            popt = result["_popt"]
            pcov = result["_pcov"]
            yhat = model(x_new, *popt)
            G = np.zeros((len(x_new), len(popt)))
            for j in range(len(popt)):
                h = 1e-6 * (abs(popt[j]) + 1e-6)
                dp = np.zeros_like(popt)
                dp[j] = h
                G[:, j] = (model(x_new, *(popt + dp)) - model(x_new, *(popt - dp))) / (2 * h)
            var = np.einsum("ij,jk,ik->i", G, pcov, G)

    var = np.clip(var, 0.0, None)
    half = t * np.sqrt(var)
    return yhat, yhat - half, yhat + half


def predict_at(result, x0):
    """Scalar convenience: (yhat, y_lower, y_upper) at a single x0."""
    yhat, ylo, yhi = evaluate(result, [x0])
    return float(yhat[0]), float(ylo[0]), float(yhi[0])
