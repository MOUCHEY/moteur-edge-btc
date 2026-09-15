"""Pointwise signal language: arithmetic, comparisons, &, |, ~ and abs only.

No Python evaluation, attributes, indexing, method calls or time transforms are
available. Missing/non-finite intermediate values suppress the signal on that
row, including under negation. Feature causality is checked by features.py.
"""
from __future__ import annotations

import ast
import math
import numbers
import operator
import re
import string
from collections.abc import Mapping

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_complex_dtype, is_numeric_dtype


class SpecError(RuntimeError):
    """An invalid strategy contract or expression; never execute it."""


_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]*\Z")
_ARITHMETIC = {ast.Add: operator.add, ast.Sub: operator.sub,
               ast.Mult: operator.mul, ast.Div: operator.truediv,
               ast.Mod: operator.mod, ast.Pow: operator.pow}
_COMPARISONS = {ast.Eq: operator.eq, ast.NotEq: operator.ne,
                ast.Lt: operator.lt, ast.LtE: operator.le,
                ast.Gt: operator.gt, ast.GtE: operator.ge}
_MAX_SOURCE = 4096
_MAX_NODES = 256


def scalar(value):
    """Copy a finite real scalar into a plain Python value; no string coercion."""
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, numbers.Integral):
        value = int(value)
        if value.bit_length() > 1024:
            raise SpecError("constante entiere trop grande")
        return value
    if isinstance(value, numbers.Real):
        value = float(value)
        if math.isfinite(value):
            return value
    raise SpecError("parametres et constantes : scalaires reels finis uniquement")


def format_expression(expr: str, params: Mapping) -> str:
    """Support {threshold} and feature_{window}, with no format traversal."""
    if not isinstance(expr, str) or not expr.strip() or len(expr) > _MAX_SOURCE:
        raise SpecError("expression absente ou trop longue")
    if not isinstance(params, Mapping):
        raise SpecError("les parametres doivent former un mapping")
    clean = {}
    for name, value in params.items():
        if not isinstance(name, str) or not _NAME.fullmatch(name) or name == "abs":
            raise SpecError("nom de parametre invalide ou reserve")
        clean[name] = scalar(value)
    parts = []
    try:
        for literal, field, spec, conversion in string.Formatter().parse(expr):
            parts.append(literal)
            if field is not None:
                if not _NAME.fullmatch(field) or spec or conversion:
                    raise SpecError("substitution autorisee : {nom} uniquement")
                if field not in clean:
                    raise SpecError(f"parametre absent : {field}")
                parts.append(repr(clean[field]))
    except ValueError as exc:
        raise SpecError("substitution de parametre invalide") from exc
    formatted = "".join(parts)
    if len(formatted) > _MAX_SOURCE:
        raise SpecError("expression trop longue apres substitution")
    return formatted


def parse(expr: str, params: Mapping) -> ast.Expression:
    """Validate the complete AST before any operation on a feature."""
    try:
        tree = ast.parse(format_expression(expr, params), mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise SpecError("syntaxe de signal invalide") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_NODES:
        raise SpecError("expression trop complexe")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Name,
               ast.Constant, ast.Load, ast.Call, ast.BitAnd, ast.BitOr,
               ast.Invert, ast.UAdd, ast.USub, *_ARITHMETIC, *_COMPARISONS)
    for node in nodes:
        if isinstance(node, ast.BoolOp) or isinstance(node, ast.Not):
            raise SpecError("utiliser & et | (et ~), pas and/or/not")
        if not isinstance(node, allowed):
            raise SpecError(f"construction interdite : {type(node).__name__}")
        if isinstance(node, ast.Constant):
            scalar(node.value)
        if isinstance(node, ast.Name) and not _NAME.fullmatch(node.id):
            raise SpecError("nom interdit")
        if isinstance(node, ast.Call):
            if (not isinstance(node.func, ast.Name) or node.func.id != "abs"
                    or len(node.args) != 1 or node.keywords):
                raise SpecError("seul l'appel abs(expression) est autorise")
    return tree


def evaluate(expr: str, feats: pd.DataFrame, params: Mapping) -> pd.Series:
    """Return a boolean Series aligned exactly to the supplied feature rows."""
    tree = parse(expr, params)
    if not isinstance(feats, pd.DataFrame) or not feats.columns.is_unique:
        raise SpecError("features attendues : DataFrame avec colonnes uniques")
    clean = {name: scalar(value) for name, value in params.items()}
    collision = set(clean).intersection(feats.columns)
    if collision:
        raise SpecError(f"parametres masquant des features : {sorted(collision)}")
    valid = pd.Series(True, index=feats.index, dtype=bool)

    def checked(value):
        nonlocal valid
        if isinstance(value, pd.Series):
            if not value.index.identical(feats.index):
                raise SpecError("index de signal non aligne")
            if (not (is_numeric_dtype(value.dtype) or is_bool_dtype(value.dtype))
                    or is_complex_dtype(value.dtype)):
                raise SpecError("une feature doit etre numerique ou booleenne")
            finite = np.isfinite(value.to_numpy(dtype=float, na_value=np.nan))
            valid &= pd.Series(finite, index=feats.index)
            return value
        return scalar(value)

    def boolean(value):
        if isinstance(value, pd.Series):
            return is_bool_dtype(value.dtype)
        return isinstance(value, bool)

    def numeric(value):
        if boolean(value):
            raise SpecError("operation arithmetique sur un booleen interdite")
        return value

    def visit(node):
        if isinstance(node, ast.Constant):
            return checked(node.value)
        if isinstance(node, ast.Name):
            if node.id in feats.columns:
                return checked(feats[node.id])
            if node.id in clean:
                return clean[node.id]
            raise SpecError(f"feature ou parametre inconnu : {node.id}")
        if isinstance(node, ast.Call):
            return checked(abs(numeric(visit(node.args[0]))))
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            if isinstance(node.op, ast.Invert):
                if not boolean(value):
                    raise SpecError("~ exige une expression booleenne")
                return checked(~value if isinstance(value, pd.Series) else not value)
            value = numeric(value)
            return checked(+value if isinstance(node.op, ast.UAdd) else -value)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, (ast.BitAnd, ast.BitOr)):
                if not (boolean(left) and boolean(right)):
                    raise SpecError("& et | exigent des expressions booleennes")
                op = operator.and_ if isinstance(node.op, ast.BitAnd) else operator.or_
            else:
                left, right = numeric(left), numeric(right)
                if isinstance(node.op, ast.Pow):
                    if isinstance(right, pd.Series) or abs(right) > 32:
                        raise SpecError("exposant scalaire borne a [-32, 32] requis")
                op = _ARITHMETIC[type(node.op)]
            with np.errstate(all="ignore"):
                return checked(op(left, right))
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            result = True
            for op, item in zip(node.ops, node.comparators):
                right = visit(item)
                result = checked(operator.and_(result, _COMPARISONS[type(op)](left, right)))
                left = right
            return result
        raise SpecError(f"construction interdite : {type(node).__name__}")

    try:
        out = visit(tree.body)
    except SpecError:
        raise
    except (ValueError, TypeError, OverflowError, ZeroDivisionError, RecursionError) as exc:
        raise SpecError(f"expression invalide : {type(exc).__name__}") from exc
    if not isinstance(out, pd.Series) or not boolean(out):
        raise SpecError("le signal doit produire une Series booleenne")
    return (out.fillna(False).astype(bool) & valid).rename(None)
