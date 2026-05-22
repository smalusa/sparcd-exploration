import marimo

__generated_with = "0.23.8"
app = marimo.App(
    width="medium",
    app_title="SPARC'd Exploration",
    auto_download=["html"],
)


@app.cell(hide_code=True)
def _():
    import os
    from pathlib import Path
    from urllib.parse import urlparse

    import marimo as mo
    from dotenv import load_dotenv
    from minio import Minio

    # Load .env strictly for prefilling the form — if absent, the form is blank.
    load_dotenv(Path(".env"))

    DEFAULT_ENDPOINT = os.getenv("SPARCD_S3_ENDPOINT", "")
    DEFAULT_ACCESS = os.getenv("SPARCD_S3_ACCESS_KEY", "")
    DEFAULT_SECRET = os.getenv("SPARCD_S3_SECRET_KEY", "")
    DEFAULT_SECURE = os.getenv("SPARCD_S3_SECURE", "true").lower() == "true"
    return (
        DEFAULT_ACCESS,
        DEFAULT_ENDPOINT,
        DEFAULT_SECRET,
        DEFAULT_SECURE,
        Minio,
        mo,
        urlparse,
    )


@app.cell(hide_code=True)
def _(DEFAULT_ACCESS, DEFAULT_ENDPOINT, DEFAULT_SECRET, DEFAULT_SECURE, mo):
    # S3 / MinIO credentials. Edit and click Submit. Values prefill from .env if present.
    _endpoint_in = mo.ui.text(
        value=DEFAULT_ENDPOINT,
        label="Endpoint",
        placeholder="host[:port] or https://host",
        full_width=True,
    )
    _access_in = mo.ui.text(
        value=DEFAULT_ACCESS,
        label="Access key",
        full_width=True,
    )
    _secret_in = mo.ui.text(
        value=DEFAULT_SECRET,
        label="Secret key",
        kind="password",
        full_width=True,
    )
    _secure_in = mo.ui.checkbox(value=DEFAULT_SECURE, label="Use HTTPS (when no scheme in endpoint)")

    creds_form = (
        mo.md("""
        {endpoint}

        {access}

        {secret}

        {secure}
        """)
        .batch(endpoint=_endpoint_in, access=_access_in, secret=_secret_in, secure=_secure_in)
        .form(label="Credentials", bordered=True, show_clear_button=True)
    )
    creds_form
    return (creds_form,)


@app.cell(hide_code=True)
def _(
    DEFAULT_ACCESS,
    DEFAULT_ENDPOINT,
    DEFAULT_SECRET,
    DEFAULT_SECURE,
    Minio,
    creds_form,
    mo,
    urlparse,
):
    # Build the MinIO client from the submitted credentials, falling back to .env
    # defaults on first load (so a working .env keeps the app usable without re-submitting).
    _form_value = creds_form.value
    if _form_value is None:
        _creds = {
            "endpoint": DEFAULT_ENDPOINT,
            "access": DEFAULT_ACCESS,
            "secret": DEFAULT_SECRET,
            "secure": DEFAULT_SECURE,
        } if (DEFAULT_ENDPOINT and DEFAULT_ACCESS and DEFAULT_SECRET) else None
    else:
        _creds = _form_value

    mo.stop(
        not _creds or not _creds.get("endpoint") or not _creds.get("access") or not _creds.get("secret"),
        mo.md("**\u26a0\ufe0f Submit credentials above to load data.**"),
    )

    _raw = _creds["endpoint"]
    if "://" in _raw:
        _u = urlparse(_raw)
        _ep = _u.netloc
        _secure = _u.scheme == "https"
    else:
        _ep = _raw
        _secure = bool(_creds["secure"])

    client = Minio(_ep, access_key=_creds["access"], secret_key=_creds["secret"], secure=_secure)
    _creds_source = "form" if _form_value is not None else ".env defaults"
    mo.md(f"\u2705 Connected to `{_ep}` (secure={_secure}) \u00b7 from {_creds_source}.")
    return (client,)


@app.cell(hide_code=True)
def _(client, mo):
    # Collection registry. Reads every sparcd-<uuid> bucket's collection.json
    # so the picker can show human-readable names.
    import json as _json
    from minio.error import S3Error as _S3Error

    _buckets = [b.name for b in client.list_buckets() if b.name.startswith("sparcd-")]

    collections_registry = []
    for _b in _buckets:
        _uuid = _b.removeprefix("sparcd-")
        try:
            _meta = _json.loads(client.get_object(_b, f"Collections/{_uuid}/collection.json").read())
            _name = _meta.get("nameProperty") or _meta.get("name") or _uuid
            _org = _meta.get("organizationProperty") or ""
            collections_registry.append({"bucket": _b, "uuid": _uuid, "name": _name, "org": _org})
        except _S3Error:
            continue

    collections_registry.sort(key=lambda r: (r["name"].strip().lower(), r["bucket"]))
    mo.md(f"_Discovered {len(collections_registry)} collection(s)._")
    return (collections_registry,)


@app.cell(hide_code=True)
def _(collections_registry, mo):
    # Multi-select collection picker.
    _options = {f"{c['name']}   ({c['org']})" if c['org'] else c['name']: c['bucket']
                for c in collections_registry}

    _default = next(
        (k for k in _options if "educational" in k.lower() and "test" in k.lower()),
        next(iter(_options), None),
    )

    collection_picker = mo.ui.multiselect(
        options=_options,
        value=[_default] if _default else [],
        label="Collections (search and pick one or more)",
        full_width=True,
    )
    collection_picker
    return (collection_picker,)


@app.cell(hide_code=True)
def _(collection_picker):
    # Selected buckets + their UUIDs / prefixes (lists, plural).
    BUCKETS = list(collection_picker.value or [])
    COLLECTION_UUIDS = [b.removeprefix("sparcd-") for b in BUCKETS]
    UPLOADS_PREFIXES = [(b, f"Collections/{u}/Uploads/")
                        for b, u in zip(BUCKETS, COLLECTION_UUIDS)]
    None
    return BUCKETS, UPLOADS_PREFIXES


@app.cell(hide_code=True)
def _(BUCKETS, collection_picker, mo):
    _picked_labels = [k for k, v in (collection_picker.options or {}).items() if v in BUCKETS]
    _label_str = ", ".join(_picked_labels) if _picked_labels else "(no collection selected)"
    mo.md(
        f"""
        # SPARC'd \u2014 {_label_str}

        Pick one or more collections, filter by date and common-name tags, and
        click (or Shift-click) map markers to drill in.
        """
    )
    return


@app.cell(hide_code=True)
def _(BUCKETS, UPLOADS_PREFIXES, client, mo):
    import csv
    import io

    import polars as pl


    def _read_csv(bucket: str, key: str) -> list[list[str]]:
        raw = client.get_object(bucket, key).read().decode("utf-8", errors="replace")
        return [row for row in csv.reader(io.StringIO(raw)) if row]


    DEPLOY_COLS = ["deployment_id", "location_id", "location_name",
                   "longitude", "latitude"]
    MEDIA_COLS = ["media_path", "deployment_id", "_p2", "_p3", "_p4",
                  "_p5", "file_name", "mime_type"]
    OBS_COLS = ["_p0", "deployment_id", "_p2", "media_path", "timestamp",
                "_p5", "_p6", "_p7", "scientific_name", "count",
                "_p10", "_p11", "_p12", "_p13", "_p14", "_p15", "_p16",
                "_p17", "_p18", "tags"]


    def _to_df(rows, buckets, cols):
        if not rows:
            sch = {c: pl.Utf8 for c in cols}
            sch["bucket"] = pl.Utf8
            return pl.DataFrame({c: [] for c in cols + ["bucket"]}, schema=sch)
        width = len(cols)
        fixed = [(r + [""] * width)[:width] for r in rows]
        df = pl.DataFrame(fixed, schema=cols, orient="row")
        df = df.with_columns(pl.Series("bucket", buckets))
        return df.select(cols + ["bucket"])


    _dep_rows, _dep_buckets = [], []
    _media_rows, _media_buckets = [], []
    _obs_rows, _obs_buckets = [], []
    total_uploads = 0

    for bucket, prefix in UPLOADS_PREFIXES:
        try:
            uploads = [
                o.object_name
                for o in client.list_objects(bucket, prefix=prefix, recursive=False)
                if o.is_dir and o.object_name != prefix
            ]
        except Exception:
            uploads = []
        total_uploads += len(uploads)
        for up in uploads:
            try:
                rows = _read_csv(bucket, up + "deployments.csv")
                _dep_rows += rows
                _dep_buckets += [bucket] * len(rows)
            except Exception:
                pass
            try:
                rows = _read_csv(bucket, up + "media.csv")
                _media_rows += rows
                _media_buckets += [bucket] * len(rows)
            except Exception:
                pass
            try:
                rows = _read_csv(bucket, up + "observations.csv")
                _obs_rows += rows
                _obs_buckets += [bucket] * len(rows)
            except Exception:
                pass

    deployments = (
        _to_df(_dep_rows, _dep_buckets, DEPLOY_COLS + [f"_d{i}" for i in range(50)])
        .select(DEPLOY_COLS + ["bucket"])
        .with_columns(
            pl.col("latitude").cast(pl.Float64, strict=False),
            pl.col("longitude").cast(pl.Float64, strict=False),
        )
        .filter(pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null())
    )
    media = (
        _to_df(_media_rows, _media_buckets, MEDIA_COLS + [f"_m{i}" for i in range(50)])
        .select(MEDIA_COLS + ["bucket"])
    )
    observations = (
        _to_df(_obs_rows, _obs_buckets, OBS_COLS + [f"_o{i}" for i in range(50)])
        .select(OBS_COLS + ["bucket"])
    )

    mo.md(
        f"**Loaded:** {len(BUCKETS)} collection(s) \u00b7 "
        f"{total_uploads} upload(s) \u00b7 "
        f"{deployments.height} deployment row(s) \u00b7 "
        f"{media.height} media \u00b7 "
        f"{observations.height} observation(s)."
    )
    return deployments, media, observations, pl


@app.cell(hide_code=True)
def _(mo, observations, pl):
    # Date range filter (applied to observation timestamps).
    import datetime as _dt

    _ts = observations.filter(pl.col("timestamp").str.len_chars() >= 10)["timestamp"]
    if _ts.len() > 0:
        _min_str = _ts.min()[:10]
        _max_str = _ts.max()[:10]
        _min_d = _dt.date.fromisoformat(_min_str)
        _max_d = _dt.date.fromisoformat(_max_str)
    else:
        _min_d = _dt.date(2010, 1, 1)
        _max_d = _dt.date(2030, 12, 31)

    date_range = mo.ui.date_range(
        start=_min_d,
        stop=_max_d,
        value=(_min_d, _max_d),
        label=f"Date range (data spans {_min_d} \u2192 {_max_d})",
        full_width=True,
    )
    date_range
    return (date_range,)


@app.cell(hide_code=True)
def _(mo, observations, pl):
    # Common-name filters. Either or both can be used.
    #  - Include only: empty means all are eligible; otherwise an observation must
    #    have at least one of these common names to survive.
    #  - Exclude: any observation whose common names are *all* excluded is dropped.
    _common_names_all = (
        observations.filter(pl.col("tags").str.contains(r"\[COMMONNAME:"))
        .with_columns(pl.col("tags").str.extract_all(r"COMMONNAME:([^\]]+)").alias("_names"))
        .explode("_names")
        .with_columns(pl.col("_names").str.replace(r"COMMONNAME:", "").alias("common_name"))
        .group_by("common_name").len()
        .sort("len", descending=True)
    )
    _options_list = _common_names_all["common_name"].to_list()
    _default_excluded = [n for n in _options_list if any(k in n.lower() for k in ("ghost", "test"))]

    include_common = mo.ui.multiselect(
        options=_options_list,
        value=[],
        label="Include only (empty = all). Use this for \"only show X species\".",
        full_width=True,
    )
    exclude_common = mo.ui.multiselect(
        options=_options_list,
        value=_default_excluded,
        label="Exclude (drop these tags).",
        full_width=True,
    )
    mo.vstack([include_common, exclude_common])
    return exclude_common, include_common


@app.cell(hide_code=True)
def _(date_range, exclude_common, include_common, media, observations, pl):
    # Apply common-name include/exclude AND date-range filters.
    _included = set(include_common.value or [])
    _excluded = set(exclude_common.value or [])
    _d_start, _d_end = date_range.value
    _d_start_s, _d_end_s = str(_d_start), str(_d_end)

    _obs_dated = observations.filter(
        (pl.col("timestamp").str.len_chars() < 10)
        | ((pl.col("timestamp").str.slice(0, 10) >= _d_start_s)
           & (pl.col("timestamp").str.slice(0, 10) <= _d_end_s))
    )

    # Decorate observations with their parsed common-name list so we can filter both ways.
    _obs_with_names = (
        _obs_dated
        .with_columns(
            pl.col("tags").str.extract_all(r"COMMONNAME:([^\]]+)").alias("_names_raw")
        )
        .with_columns(
            pl.col("_names_raw")
            .list.eval(pl.element().str.replace("COMMONNAME:", ""))
            .alias("_common_names")
        )
    )

    # Include: keep iff list intersects with _included (when non-empty).
    if _included:
        _included_lit = pl.lit(list(_included))
        _obs_with_names = _obs_with_names.with_columns(
            pl.col("_common_names").list.set_intersection(_included_lit)
            .list.len().alias("_inc_hits")
        ).filter(pl.col("_inc_hits") > 0).drop("_inc_hits")

    # Exclude: drop iff every common name on the row is in _excluded.
    if _excluded:
        _excluded_lit = pl.lit(list(_excluded))
        _obs_with_names = _obs_with_names.with_columns(
            pl.col("_common_names").list.set_difference(_excluded_lit)
            .list.len().alias("_kept_names")
        ).filter(
            (pl.col("_common_names").list.len() == 0) | (pl.col("_kept_names") > 0)
        ).drop("_kept_names")

    observations_filtered = _obs_with_names.drop("_names_raw", "_common_names")

    _kept_paths = observations_filtered["media_path"].unique().to_list()
    _dated_obs_paths = _obs_dated["media_path"].unique().to_list()
    media_filtered = media.filter(
        pl.col("media_path").is_in(_kept_paths)
        | ~pl.col("media_path").is_in(_dated_obs_paths)
    )
    None
    return media_filtered, observations_filtered


@app.cell(hide_code=True)
def _(deployments, media_filtered, mo, observations_filtered, pl):
    # Normalize deployments; attach image counts using the FILTERED media/observations.
    _locations_raw = (
        deployments
        .with_columns(
            pl.when(pl.col("latitude").abs() > 90)
            .then(pl.col("longitude"))
            .otherwise(pl.col("latitude"))
            .alias("lat_fixed"),
            pl.when(pl.col("latitude").abs() > 90)
            .then(pl.col("latitude"))
            .otherwise(pl.col("longitude"))
            .alias("lng_fixed"),
        )
        .drop("latitude", "longitude")
        .rename({"lat_fixed": "latitude", "lng_fixed": "longitude"})
        .filter(pl.col("location_id") != "0000")
        .filter(pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null())
    )

    _image_counts = media_filtered.group_by("deployment_id").agg(
        pl.col("media_path").n_unique().alias("image_count")
    )
    _obs_counts = observations_filtered.group_by("deployment_id").agg(
        pl.col("media_path").n_unique().alias("tagged_image_count")
    )

    locations = (
        _locations_raw
        .join(_image_counts, on="deployment_id", how="left")
        .join(_obs_counts, on="deployment_id", how="left")
        .group_by("location_id", "location_name", "latitude", "longitude")
        .agg(
            pl.col("deployment_id").unique().alias("deployment_ids"),
            pl.col("image_count").sum().fill_null(0).alias("image_count"),
            pl.col("tagged_image_count").sum().fill_null(0).alias("tagged_image_count"),
        )
        .sort("location_name")
    )

    mo.ui.table(
        locations.drop("deployment_ids"),
        show_column_summaries=False,
        show_data_types=False,
        selection=None,
        pagination=True,
    )
    return (locations,)


@app.cell(hide_code=True)
def _(camera_map, locations):
    # Selection bridge: derive the chosen list of location_ids from plotly.
    _v = camera_map.value

    def _resolve_location_id(point: dict) -> str | None:
        cd = point.get("customdata")
        if cd:
            return cd[0] if isinstance(cd, (list, tuple)) else cd
        idx = point.get("pointIndex")
        if isinstance(idx, int):
            ids = locations["location_id"].to_list()
            if 0 <= idx < len(ids):
                return ids[idx]
        return None

    selected_location_ids = []
    if _v:
        seen = set()
        for p in _v:
            lid = _resolve_location_id(p)
            if lid and lid not in seen:
                seen.add(lid)
                selected_location_ids.append(lid)
    return (selected_location_ids,)


@app.cell(hide_code=True)
def _(locations, mo):
    # Map of camera locations. Click a marker to select; Shift+click to add more,
    # or use the box/lasso tools in the toolbar to select an area.
    import plotly.graph_objects as go

    _lats = locations["latitude"].to_list()
    _lngs = locations["longitude"].to_list()
    _names = locations["location_name"].to_list()
    _ids = locations["location_id"].to_list()
    _counts = locations["image_count"].to_list()
    _tagged = locations["tagged_image_count"].to_list()

    _center = (
        sum(_lats) / len(_lats) if _lats else 32.0,
        sum(_lngs) / len(_lngs) if _lngs else -110.0,
    )

    camera_fig = go.Figure(
        go.Scattermap(
            lat=_lats,
            lon=_lngs,
            mode="markers",
            marker=dict(
                size=[18 + min(c, 200) / 10 for c in _counts],
                color="#e74c3c",
                opacity=0.85,
            ),
            text=_names,
            customdata=list(zip(_ids, _counts, _tagged)),
            hovertemplate=(
                "<b>%{text}</b><br>"
                "id: %{customdata[0]}<br>"
                "images: %{customdata[1]}  \u00b7  tagged: %{customdata[2]}<br>"
                "%{lat:.4f}, %{lon:.4f}<br>"
                "<i>click \u00b7 shift-click \u00b7 box/lasso to select</i><extra></extra>"
            ),
            selected=dict(marker=dict(color="#27ae60", opacity=1.0)),
            unselected=dict(marker=dict(opacity=0.6)),
        )
    )
    camera_fig.update_layout(
        map=dict(style="open-street-map", center=dict(lat=_center[0], lon=_center[1]), zoom=8),
        margin=dict(l=0, r=0, t=0, b=0),
        height=480,
        showlegend=False,
        clickmode="event+select",
        dragmode="pan",
    )

    camera_map = mo.ui.plotly(camera_fig)
    camera_map
    return (camera_map,)


@app.cell(hide_code=True)
def _(locations, mo, pl, selected_location_ids):
    if not selected_location_ids:
        mo.md("### \u2191 Click, Shift-click, or box-select markers to load the report")
    else:
        _rows = locations.filter(pl.col("location_id").is_in(selected_location_ids))
        _names = ", ".join(_rows["location_name"].to_list())
        _img = int(_rows["image_count"].sum())
        _tag = int(_rows["tagged_image_count"].sum())
        mo.md(
            f"### {len(selected_location_ids)} location(s): {_names}  \n"
            f"{_img} image(s) \u00b7 {_tag} tagged (after filters)"
        )
    return


@app.cell(hide_code=True)
def _(
    date_range,
    exclude_common,
    locations,
    media_filtered,
    mo,
    observations_filtered,
    pl,
    selected_location_ids,
):
    from html import escape as _esc

    def _stats_html(loc, total, tagged, untagged, distinct, date_range_str, tagging_pct):
        def _row(label, value, color="#111"):
            return ("<div style='display:flex; justify-content:space-between; "
                    "padding:4px 0; border-bottom:1px solid #eee;'>"
                    f"<span style='color:#666;'>{_esc(label)}</span>"
                    f"<span style=\"font-weight:600; color:{color};\">{_esc(str(value))}</span></div>")
        return (
            "<div style='padding:0 8px;'>"
            + _row("Total images", total)
            + _row("Tagged", f"{tagged}  ({tagging_pct})", color="#27ae60")
            + _row("Untagged", untagged, color="#c0392b" if untagged else "#999")
            + _row("Distinct species", distinct)
            + _row("Date range", date_range_str)
            + "</div>"
        )

    def _table_rows_html(df, label_col):
        rows = []
        for r in df.iter_rows(named=True):
            rows.append(
                f"<tr><td style='padding:3px 8px 3px 0;'>{_esc(str(r[label_col]))}</td>"
                f"<td style='padding:3px 0; text-align:right; font-variant-numeric:tabular-nums; color:#444;'>{r['images']}</td></tr>"
            )
        return "<table style='width:100%; border-collapse:collapse; font-size:13px;'>" + "".join(rows) + "</table>"

    def _build_section(title, df, label_col, max_rows=8):
        header = mo.md(f"**{title}**")
        if df.height == 0:
            return mo.vstack([header, mo.md("<span style=\"color:#999;\">none</span>")])
        if df.height <= max_rows:
            return mo.vstack([header, mo.Html(_table_rows_html(df, label_col))])
        top_html = _table_rows_html(df.head(max_rows), label_col)
        rest_html = _table_rows_html(df.slice(max_rows, df.height - max_rows), label_col)
        label = f"Show {df.height - max_rows} more"
        return mo.vstack([
            header,
            mo.Html(top_html),
            mo.accordion({label: mo.Html(rest_html)}),
        ])

    if not selected_location_ids:
        location_summary_card = mo.md("")
    else:
        _rows = locations.filter(pl.col("location_id").is_in(selected_location_ids))
        _dep_ids = [d for ds in _rows["deployment_ids"].to_list() for d in ds]

        _media_loc = media_filtered.filter(pl.col("deployment_id").is_in(_dep_ids)).unique("media_path")
        _obs_loc = observations_filtered.filter(pl.col("deployment_id").is_in(_dep_ids))

        _total = _media_loc.height
        _tagged = _obs_loc["media_path"].unique().len()
        _untagged = max(0, _total - _tagged)

        _sci_clean = (
            _obs_loc
            .filter(pl.col("scientific_name").str.len_chars() >= 3)
            .filter(pl.col("scientific_name") != "")
        )
        _species_counts = (
            _sci_clean.group_by("scientific_name").len()
            .rename({"len": "images"}).sort("images", descending=True)
        )
        _distinct_species = _species_counts.height

        _common = (
            _obs_loc.filter(pl.col("tags").str.contains(r"\[COMMONNAME:"))
            .with_columns(pl.col("tags").str.extract_all(r"COMMONNAME:([^\]]+)").alias("_names"))
            .explode("_names")
            .with_columns(pl.col("_names").str.replace(r"COMMONNAME:", "").alias("common_name"))
            .drop("_names")
        )
        _common_counts = (
            _common.group_by("common_name").len()
            .rename({"len": "images"}).sort("images", descending=True)
        )

        _dates = _obs_loc.filter(pl.col("timestamp").str.len_chars() >= 10)["timestamp"]
        _date_range_str = "\u2014"
        if _dates.len() > 0:
            _d_min = _dates.min()[:10]
            _d_max = _dates.max()[:10]
            _date_range_str = f"{_d_min} \u2192 {_d_max}" if _d_min != _d_max else _d_min
        _tagging_pct = f"{(_tagged / _total * 100):.0f}%" if _total else "\u2014"

        _stats_section = mo.vstack([
            mo.md("**Overview**"),
            mo.Html(_stats_html(_rows, _total, _tagged, _untagged, _distinct_species, _date_range_str, _tagging_pct)),
        ])
        _common_section = _build_section("Top common names", _common_counts, "common_name")
        _species_section = _build_section("Top species (scientific)", _species_counts, "scientific_name")

        _filter_notes = []
        if exclude_common.value:
            _filter_notes.append(f"excluding: <i>{_esc(', '.join(exclude_common.value))}</i>")
        _filter_notes.append(f"date: {date_range.value[0]} \u2192 {date_range.value[1]}")
        _filter_notes.append(f"{len(selected_location_ids)} location(s) selected")
        _notes = mo.Html(
            "<div style='margin:6px 0 0; font-size:12px; color:#777;'>"
            + " \u00b7 ".join(_filter_notes) + "</div>"
        )

        location_summary_card = mo.vstack([
            mo.hstack(
                [_stats_section, _common_section, _species_section],
                widths="equal",
                gap=2,
                align="start",
            ),
            _notes,
        ])

    location_summary_card
    return


@app.cell(hide_code=True)
def _(
    locations,
    media_filtered,
    observations_filtered,
    pl,
    selected_location_ids,
):
    # Only tagged images that survived the filter feed the thumbnail grid.
    if not selected_location_ids:
        selected_images_all = pl.DataFrame()
        selected_total = 0
    else:
        _rows = locations.filter(pl.col("location_id").is_in(selected_location_ids))
        _dep_ids = [d for ds in _rows["deployment_ids"].to_list() for d in ds]
        selected_images_all = (
            media_filtered
            .filter(pl.col("deployment_id").is_in(_dep_ids))
            .select("media_path", "file_name", "deployment_id", "bucket")
            .unique(subset=["media_path"])
            .join(
                observations_filtered
                .select("media_path", "scientific_name", "count", "tags", "timestamp")
                .unique(subset=["media_path"]),
                on="media_path",
                how="inner",  # was "left" — drops untagged frames from the display
            )
            .sort("media_path")
        )
        selected_total = selected_images_all.height
    None
    return selected_images_all, selected_total


@app.cell(hide_code=True)
def _(
    PAGE_SIZE,
    client,
    mo,
    page_select,
    selected_images_all,
    selected_location_ids,
    selected_total,
):
    from datetime import timedelta
    from html import escape

    def _presign_row(bucket: str, path: str) -> str:
        return client.presigned_get_object(bucket, path, expires=timedelta(minutes=30))

    def _parse_tags(raw: str) -> str:
        if not raw:
            return ""
        parts = [p.split(":", 1)[1] for p in raw.strip("[]").split("][") if ":" in p]
        return ", ".join(parts)

    if not selected_location_ids:
        thumbnail_grid = mo.md("_(click a marker on the map)_")
    elif selected_total == 0:
        thumbnail_grid = mo.md("**No tagged images match the current filters** at the selected location(s).")
    else:
        _page = int(page_select.value or "1")
        _start = (_page - 1) * PAGE_SIZE
        _end = min(_start + PAGE_SIZE, selected_total)
        _page_df = selected_images_all.slice(_start, PAGE_SIZE)
        _total_pages = max(1, -(-selected_total // PAGE_SIZE))

        _tiles = []
        for _row in _page_df.iter_rows(named=True):
            _url = _presign_row(_row["bucket"], _row["media_path"])
            _tag = _parse_tags(_row.get("tags") or "")
            _sci = _row.get("scientific_name") or ""
            _ts = (_row.get("timestamp") or "").replace("T", " ")[:19]
            _caption = " \u00b7 ".join(x for x in [_tag, _sci, _ts] if x)
            _u = escape(_url, quote=True)
            _f = escape(_row["file_name"])
            _m = escape(_caption) if _caption else "&nbsp;"
            _tiles.append(f"""
              <figure style="margin:0; display:flex; flex-direction:column; gap:4px;">
                <a href="{_u}" target="_blank" rel="noopener" title="Open full image"
                   style="display:block; cursor:zoom-in;">
                  <img src="{_u}" loading="lazy"
                       style="width:100%; aspect-ratio:4/3; object-fit:cover;
                              border-radius:6px; background:#222; display:block;
                              transition:transform 0.15s ease;"
                       onmouseover="this.style.transform='scale(1.02)'"
                       onmouseout="this.style.transform='scale(1)'" />
                </a>
                <figcaption style="font-size:12px; line-height:1.3;">
                  <div style="font-weight:600; color:var(--marimo-text,#111);">{_f}</div>
                  <div style="color:var(--marimo-muted,#666); word-break:break-word;">{_m}</div>
                </figcaption>
              </figure>""")
        _grid = ('<div style="display:grid; '
                 'grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); '
                 'gap:12px; margin-top:8px;">'
                 + "".join(_tiles) + "</div>")
        _status = mo.md(
            f"**Page {_page} of {_total_pages}** \u00b7 "
            f"images {_start + 1}\u2013{_end} of {selected_total} (tagged only). "
            f"<sub>Click a thumbnail to open the full image in a new tab.</sub>"
        )
        thumbnail_grid = mo.vstack([_status, mo.Html(_grid)])

    thumbnail_grid
    return


@app.cell(hide_code=True)
def _(mo, selected_location_ids, selected_total):
    # Page selector. 12 thumbnails per page.
    PAGE_SIZE = 12

    def _make_page_selector():
        _trigger = tuple(selected_location_ids)  # re-create whenever selection changes
        _pages = max(1, -(-selected_total // PAGE_SIZE))
        return mo.ui.dropdown(
            options=[str(i) for i in range(1, _pages + 1)],
            value="1",
            label=f"Page (1\u2013{_pages})",
        )

    page_select = _make_page_selector()
    page_select
    return PAGE_SIZE, page_select


if __name__ == "__main__":
    app.run()
