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
    from minio import Minio

    # .env loading: only when python-dotenv is available (i.e. running locally â€”
    # Pyodide / WASM doesn\'t have it by default and has no filesystem to read).
    try:
        from dotenv import load_dotenv as _load_dotenv
        _load_dotenv(Path(".env"))
    except ImportError:
        pass

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
    from pathlib import Path as _Path

    _endpoint_in = mo.ui.text(
        value=DEFAULT_ENDPOINT,
        label="Endpoint",
        placeholder="host[:port] or https://host",
        full_width=False,
    )
    _access_in = mo.ui.text(
        value=DEFAULT_ACCESS,
        label="Access key",
        full_width=False,
    )
    _secret_in = mo.ui.text(
        value=DEFAULT_SECRET,
        label="Secret key",
        kind="password",
        full_width=False,
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
    _logo_path = _Path("assets/sparcd-logo-sharp.png")
    _logo = mo.image(
        src=str(_logo_path),
        alt="SPARC'd logo",
        width=132,
    ) if _logo_path.exists() else mo.md("")
    _project_header = mo.hstack(
        [
            mo.Html(
                "<div style='font-size:34px; line-height:1.12; font-weight:800;'>"
                "University of Arizona Wild Cat Research & Conservation Center"
                "</div>"
            ),
            _logo,
        ],
        widths=[5, 1],
        align="center",
    )
    mo.Html(
        "<style>"
        ".sparcd-creds-wrap form { max-width: 440px; }"
        ".sparcd-creds-wrap input { max-width: 360px; }"
        ".sparcd-creds-wrap .markdown { margin-block: 0.2rem; }"
        "</style>"
    )
    mo.vstack([
        _project_header,
        mo.Html("<div class='sparcd-creds-wrap'>"),
        mo.hstack([creds_form], widths=[1]),
        mo.Html("</div>"),
    ])
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
    None
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
        label="Collection",
        full_width=False,
    )
    None
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
def _(BUCKETS, mo):
    intro_text = mo.md(
        "Filter by range, site, time, and species, then click or Shift-click map markers to drill in."
    )
    intro_text
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
                   "longitude", "latitude", "_d5", "_d6", "_d7",
                   "_d8", "_d9", "_d10", "_d11", "elevation"]
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
        _to_df(_dep_rows, _dep_buckets, DEPLOY_COLS + [f"_d{i}" for i in range(13, 50)])
        .select(DEPLOY_COLS + ["bucket"])
        .with_columns(
            pl.col("latitude").cast(pl.Float64, strict=False),
            pl.col("longitude").cast(pl.Float64, strict=False),
            pl.col("elevation").cast(pl.Float64, strict=False),
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
    # Date filters are displayed with the rest of the query controls.
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

    start_date_filter = mo.ui.date(
        start=_min_d,
        stop=_max_d,
        value=_min_d,
        label="Start date",
        full_width=False,
    )
    end_date_filter = mo.ui.date(
        start=_min_d,
        stop=_max_d,
        value=_max_d,
        label="End date",
        full_width=False,
    )
    None
    return end_date_filter, start_date_filter


@app.cell(hide_code=True)
def _(collection_picker, deployments, end_date_filter, mo, observations, pl, start_date_filter):
    # Query filters. Options are built in Python for Pyodide/WASM compatibility.
    import re as _re

    _pat = _re.compile(r"COMMONNAME:([^\]]+)")
    _species_counts = {}
    for _t in observations["tags"].to_list():
        if not _t:
            continue
        for _m in _pat.findall(_t):
            _species_counts[_m] = _species_counts.get(_m, 0) + 1
    _species_options = sorted(_species_counts, key=lambda k: (-_species_counts[k], k.lower()))
    _default_excluded = [n for n in _species_options if any(k in n.lower() for k in ("ghost", "test"))]

    _site_options = sorted(
        {v for v in deployments["location_id"].to_list() if v and v != "0000"}
    )
    _range_options = sorted({v[:3] for v in _site_options if len(v) >= 3})
    _year_options = sorted(
        {str(v)[:4] for v in observations["timestamp"].to_list() if v and len(str(v)) >= 4}
    )
    _month_options = sorted(
        {str(v)[5:7] for v in observations["timestamp"].to_list() if v and len(str(v)) >= 7}
    )
    _elev = deployments.filter(pl.col("elevation").is_not_null())["elevation"]
    if _elev.len() > 0:
        _e_min = int(_elev.min())
        _e_max = int(_elev.max())
    else:
        _e_min = 0
        _e_max = 0

    mountain_range_filter = mo.ui.multiselect(
        options=_range_options,
        value=[],
        label="Mountain range",
        full_width=False,
    )
    site_code_filter = mo.ui.multiselect(
        options=_site_options,
        value=[],
        label="Site code / location",
        full_width=False,
    )
    year_filter = mo.ui.multiselect(
        options=_year_options,
        value=[],
        label="Year",
        full_width=False,
    )
    month_filter = mo.ui.multiselect(
        options=_month_options,
        value=[],
        label="Month",
        full_width=False,
    )

    include_common = mo.ui.multiselect(
        options=_species_options,
        value=[],
        label="Species",
        full_width=False,
    )
    exclude_common = mo.ui.multiselect(
        options=_species_options,
        value=_default_excluded,
        label="Exclude species/tags",
        full_width=False,
    )
    elevation_range_filter = mo.ui.range_slider(
        start=_e_min,
        stop=max(_e_min + 1, _e_max),
        step=1,
        value=[_e_min, _e_max],
        label="Elevation",
        show_value=True,
        full_width=False,
        disabled=_elev.len() == 0,
    )
    show_species_columns = mo.ui.checkbox(
        value=True,
        label="Species columns",
    )
    coordinate_format = mo.ui.dropdown(
        options={
            "Lat/long": "latlong",
            "UTM": "utm",
        },
        value="Lat/long",
        label="Coordinate display",
        full_width=False,
    )
    coordinate_method = mo.ui.dropdown(
        options={
            "Round coordinates": "round",
            "Truncate coordinates": "truncate",
        },
        value="Round coordinates",
        label="Coordinate security",
        full_width=False,
    )
    coordinate_digits = mo.ui.dropdown(
        options={
            "Exact": None,
            "0 decimals": 0,
            "1 decimal": 1,
            "2 decimals": 2,
            "3 decimals": 3,
            "4 decimals": 4,
            "5 decimals": 5,
        },
        value="3 decimals",
        label="Displayed coordinate digits",
        full_width=False,
    )
    elevation_unit = mo.ui.dropdown(
        options={
            "Meters": "meters",
            "Feet": "feet",
        },
        value="Meters",
        label="Elevation display",
        full_width=False,
    )
    mo.vstack([
        mo.md("**Query filters**"),
        mo.hstack([collection_picker, mountain_range_filter, site_code_filter], widths="equal"),
        mo.hstack([start_date_filter, end_date_filter, year_filter], widths="equal"),
        mo.hstack([month_filter, include_common, elevation_range_filter], widths="equal"),
        mo.hstack([exclude_common, show_species_columns], widths=[2, 1]),
        mo.hstack([coordinate_format, coordinate_method, coordinate_digits], widths="equal"),
        mo.hstack([elevation_unit], widths=[1]),
    ])
    return (
        coordinate_digits,
        coordinate_format,
        coordinate_method,
        elevation_unit,
        elevation_range_filter,
        exclude_common,
        include_common,
        month_filter,
        mountain_range_filter,
        show_species_columns,
        site_code_filter,
        year_filter,
    )


@app.cell(hide_code=True)
def _(
    deployments,
    elevation_range_filter,
    end_date_filter,
    exclude_common,
    include_common,
    media,
    month_filter,
    mountain_range_filter,
    observations,
    pl,
    site_code_filter,
    start_date_filter,
    year_filter,
):
    # Apply query filters (Pyodide-safe).
    import re as _re_filt

    _included = set(include_common.value or [])
    _excluded = set(exclude_common.value or [])
    _ranges = set(mountain_range_filter.value or [])
    _sites = set(site_code_filter.value or [])
    _years = set(year_filter.value or [])
    _months = set(month_filter.value or [])
    _d_start, _d_end = start_date_filter.value, end_date_filter.value
    if _d_start > _d_end:
        _d_start, _d_end = _d_end, _d_start
    _d_start_s, _d_end_s = str(_d_start), str(_d_end)
    _elev_min, _elev_max = elevation_range_filter.value

    _deployments_scope = deployments
    if _ranges:
        _deployments_scope = _deployments_scope.filter(
            pl.col("location_id").str.slice(0, 3).is_in(list(_ranges))
        )
    if _sites:
        _deployments_scope = _deployments_scope.filter(pl.col("location_id").is_in(list(_sites)))
    _deployments_scope = _deployments_scope.filter(
        pl.col("elevation").is_null()
        | ((pl.col("elevation") >= _elev_min) & (pl.col("elevation") <= _elev_max))
    )
    _deployment_ids = _deployments_scope["deployment_id"].unique().to_list()

    _obs_scope = observations.filter(pl.col("deployment_id").is_in(_deployment_ids))
    _media_scope = media.filter(pl.col("deployment_id").is_in(_deployment_ids))

    _obs_dated = _obs_scope.filter(
        (pl.col("timestamp").str.len_chars() < 10)
        | ((pl.col("timestamp").str.slice(0, 10) >= _d_start_s)
           & (pl.col("timestamp").str.slice(0, 10) <= _d_end_s))
    )
    if _years:
        _obs_dated = _obs_dated.filter(pl.col("timestamp").str.slice(0, 4).is_in(list(_years)))
    if _months:
        _obs_dated = _obs_dated.filter(pl.col("timestamp").str.slice(5, 2).is_in(list(_months)))

    if not _included and not _excluded:
        observations_filtered = _obs_dated
    else:
        _pat = _re_filt.compile(r"COMMONNAME:([^\]]+)")

        def _keep_row(t):
            names = set(_pat.findall(t)) if t else set()
            if _included and not (names & _included):
                return False
            if _excluded and names and names.issubset(_excluded):
                return False
            return True

        _mask = [_keep_row(t) for t in _obs_dated["tags"].to_list()]
        observations_filtered = _obs_dated.filter(pl.Series("_keep", _mask))

    _kept_paths = observations_filtered["media_path"].unique().to_list()
    media_filtered = _media_scope.filter(pl.col("media_path").is_in(_kept_paths))
    query_deployment_ids = observations_filtered["deployment_id"].unique().to_list()
    None
    return media_filtered, observations_filtered, query_deployment_ids


@app.cell(hide_code=True)
def _(
    coordinate_digits,
    coordinate_format,
    coordinate_method,
    deployments,
    elevation_unit,
    media_filtered,
    mo,
    observations_filtered,
    pl,
    query_deployment_ids,
    show_species_columns,
):
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
        .filter(pl.col("deployment_id").is_in(query_deployment_ids))
        .filter(pl.col("location_id") != "0000")
        .filter(pl.col("latitude").is_not_null() & pl.col("longitude").is_not_null())
        .with_columns(pl.col("location_id").str.slice(0, 3).alias("mountain_range"))
    )

    _image_counts = media_filtered.group_by("deployment_id").agg(
        pl.col("media_path").n_unique().alias("image_count")
    )
    _obs_counts = media_filtered.group_by("deployment_id").agg(
        pl.col("media_path").n_unique().alias("tagged_image_count")
    )

    locations = (
        _locations_raw
        .join(_image_counts, on="deployment_id", how="left")
        .join(_obs_counts, on="deployment_id", how="left")
        .group_by("mountain_range", "location_id", "location_name", "latitude", "longitude")
        .agg(
            pl.col("deployment_id").unique().alias("deployment_ids"),
            pl.col("elevation").mean().round(0).alias("elevation"),
            pl.col("image_count").sum().fill_null(0).alias("image_count"),
            pl.col("tagged_image_count").sum().fill_null(0).alias("tagged_image_count"),
        )
        .sort("location_name")
    )

    _locations_table = locations.drop("deployment_ids")
    if elevation_unit.value == "feet":
        _locations_table = _locations_table.with_columns(
            (pl.col("elevation") * 3.28084).round(0).alias("elevation_ft")
        ).drop("elevation")
    else:
        _locations_table = _locations_table.rename({"elevation": "elevation_m"})

    if coordinate_format.value == "utm":
        import math as _math

        def _latlon_to_utm(lat, lon):
            _zone = int((lon + 180) / 6) + 1
            _hemisphere = "N" if lat >= 0 else "S"
            _a = 6378137.0
            _ecc_sq = 0.00669438
            _k0 = 0.9996
            _lat_rad = _math.radians(lat)
            _lon_rad = _math.radians(lon)
            _lon_origin = (_zone - 1) * 6 - 180 + 3
            _lon_origin_rad = _math.radians(_lon_origin)
            _ecc_prime_sq = _ecc_sq / (1 - _ecc_sq)
            _n = _a / _math.sqrt(1 - _ecc_sq * _math.sin(_lat_rad) ** 2)
            _t = _math.tan(_lat_rad) ** 2
            _c = _ecc_prime_sq * _math.cos(_lat_rad) ** 2
            _aa = _math.cos(_lat_rad) * (_lon_rad - _lon_origin_rad)
            _m = _a * (
                (1 - _ecc_sq / 4 - 3 * _ecc_sq ** 2 / 64 - 5 * _ecc_sq ** 3 / 256) * _lat_rad
                - (3 * _ecc_sq / 8 + 3 * _ecc_sq ** 2 / 32 + 45 * _ecc_sq ** 3 / 1024) * _math.sin(2 * _lat_rad)
                + (15 * _ecc_sq ** 2 / 256 + 45 * _ecc_sq ** 3 / 1024) * _math.sin(4 * _lat_rad)
                - (35 * _ecc_sq ** 3 / 3072) * _math.sin(6 * _lat_rad)
            )
            _easting = _k0 * _n * (
                _aa + (1 - _t + _c) * _aa ** 3 / 6
                + (5 - 18 * _t + _t ** 2 + 72 * _c - 58 * _ecc_prime_sq) * _aa ** 5 / 120
            ) + 500000
            _northing = _k0 * (
                _m + _n * _math.tan(_lat_rad) * (
                    _aa ** 2 / 2
                    + (5 - _t + 9 * _c + 4 * _c ** 2) * _aa ** 4 / 24
                    + (61 - 58 * _t + _t ** 2 + 600 * _c - 330 * _ecc_prime_sq) * _aa ** 6 / 720
                )
            )
            if lat < 0:
                _northing += 10000000
            return {"utm_zone": f"{_zone}{_hemisphere}", "utm_easting": _easting, "utm_northing": _northing}

        _utm_df = pl.DataFrame(
            [_latlon_to_utm(lat, lon) for lat, lon in _locations_table.select("latitude", "longitude").iter_rows()],
            schema={"utm_zone": pl.Utf8, "utm_easting": pl.Float64, "utm_northing": pl.Float64},
        )
        _locations_table = pl.concat([_locations_table.drop("latitude", "longitude"), _utm_df], how="horizontal")

    _coord_digits = coordinate_digits.value
    if _coord_digits is not None:
        _coord_cols = ["utm_easting", "utm_northing"] if coordinate_format.value == "utm" else ["latitude", "longitude"]
        if coordinate_method.value == "truncate":
            _scale = 10 ** _coord_digits

            def _truncate_coord(v):
                return int(v * _scale) / _scale

            _locations_table = _locations_table.with_columns(
                pl.col(_coord_cols[0]).map_elements(_truncate_coord, return_dtype=pl.Float64),
                pl.col(_coord_cols[1]).map_elements(_truncate_coord, return_dtype=pl.Float64),
            )
        else:
            _locations_table = _locations_table.with_columns(
                pl.col(_coord_cols[0]).round(_coord_digits),
                pl.col(_coord_cols[1]).round(_coord_digits),
            )
    if show_species_columns.value:
        _dep_to_loc = dict(_locations_raw.select("deployment_id", "location_id").iter_rows())
        _pat_result = __import__("re").compile(r"COMMONNAME:([^\]]+)")
        _species_by_loc = {}
        _years_by_loc = {}
        _months_by_loc = {}
        for _obs in observations_filtered.select("deployment_id", "timestamp", "scientific_name", "tags").iter_rows(named=True):
            _name = _obs["scientific_name"] or ""
            _loc_id = _dep_to_loc.get(_obs["deployment_id"])
            if not _loc_id:
                continue
            _names = [_name] if len(_name) >= 3 else _pat_result.findall(_obs["tags"] or "")
            for _n in _names:
                if _n:
                    _species_by_loc.setdefault(_loc_id, set()).add(_n)
            _ts = _obs["timestamp"] or ""
            if len(_ts) >= 4:
                _years_by_loc.setdefault(_loc_id, set()).add(_ts[:4])
            if len(_ts) >= 7:
                _months_by_loc.setdefault(_loc_id, set()).add(_ts[5:7])
        _summary_ids = set(_species_by_loc) | set(_years_by_loc) | set(_months_by_loc)
        _species_summary = pl.DataFrame(
            [
                {
                    "location_id": _loc_id,
                    "years": ", ".join(sorted(_years_by_loc.get(_loc_id, set()))),
                    "months": ", ".join(sorted(_months_by_loc.get(_loc_id, set()))),
                    "species": ", ".join(sorted(_species_by_loc.get(_loc_id, set()))),
                    "species_count": len(_species_by_loc.get(_loc_id, set())),
                }
                for _loc_id in _summary_ids
            ],
            schema={
                "location_id": pl.Utf8,
                "years": pl.Utf8,
                "months": pl.Utf8,
                "species": pl.Utf8,
                "species_count": pl.Int64,
            },
        )
        _locations_table = (
            _locations_table
            .join(_species_summary, on="location_id", how="left")
            .with_columns(
                pl.col("years").fill_null(""),
                pl.col("months").fill_null(""),
                pl.col("species").fill_null(""),
                pl.col("species_count").fill_null(0),
            )
        )

    mo.ui.table(
        _locations_table,
        show_column_summaries=False,
        show_data_types=False,
        selection=None,
        pagination=True,
    )
    return (locations,)


@app.cell(hide_code=True)
def _(locations, mo, observations_filtered, pl):
    import h3 as _h3

    HEX_RESOLUTION = 6

    _loc_with_hex = locations.with_columns(
        pl.struct(["latitude", "longitude"])
        .map_elements(
            lambda s: _h3.latlng_to_cell(s["latitude"], s["longitude"], HEX_RESOLUTION),
            return_dtype=pl.Utf8,
        )
        .alias("h3_id")
    )

    _dep_to_hex = {}
    for _row in _loc_with_hex.iter_rows(named=True):
        for _d in _row["deployment_ids"]:
            _dep_to_hex[_d] = _row["h3_id"]

    _obs_with_hex = observations_filtered.with_columns(
        pl.col("deployment_id").replace_strict(_dep_to_hex, default=None).alias("h3_id")
    ).filter(pl.col("h3_id").is_not_null())

    _obs_agg = (
        _obs_with_hex
        .group_by("h3_id")
        .agg(
            pl.col("scientific_name").filter(pl.col("scientific_name").str.len_chars() >= 3).n_unique().alias("species_richness"),
            pl.col("media_path").n_unique().alias("checklists"),
            pl.col("timestamp").max().alias("most_recent"),
        )
    )
    _cam_agg = (
        _loc_with_hex
        .group_by("h3_id")
        .agg(
            pl.col("location_id").n_unique().alias("camera_count"),
            pl.col("location_id").alias("location_ids"),
            pl.col("location_name").alias("location_names"),
            pl.col("latitude").mean().alias("center_lat"),
            pl.col("longitude").mean().alias("center_lng"),
        )
    )

    hex_summary = (
        _cam_agg
        .join(_obs_agg, on="h3_id", how="left")
        .with_columns(
            pl.col("species_richness").fill_null(0),
            pl.col("checklists").fill_null(0),
            (pl.col("species_richness") / pl.col("camera_count")).fill_nan(0.0).fill_null(0.0).alias("richness_per_camera"),
            pl.col("most_recent").fill_null("\u2014"),
        )
        .sort("species_richness", descending=True)
    )

    def _to_polygon(hid):
        boundary = _h3.cell_to_boundary(hid)
        ring = [[lng, lat] for lat, lng in boundary]
        ring.append(ring[0])
        return ring

    hex_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": _hid,
                "properties": {"h3_id": _hid},
                "geometry": {"type": "Polygon", "coordinates": [_to_polygon(_hid)]},
            }
            for _hid in hex_summary["h3_id"].to_list()
        ],
    }
    mo.md(f"_Binned {locations.height} location(s) into {hex_summary.height} hex(es) at H3 resolution {HEX_RESOLUTION}._")
    return hex_geojson, hex_summary


@app.cell(hide_code=True)
def _(camera_map, hex_summary, map_display_mode, pl):
    # Selection bridge for either hex cells or exact site points.
    _v = camera_map.value if hasattr(camera_map, "value") else []

    selected_location_ids = []
    if _v:
        if map_display_mode.value == "points":
            _seen = set()
            for _p in _v:
                _cd = _p.get("customdata")
                if _cd:
                    _lid = _cd[0] if isinstance(_cd, (list, tuple)) else _cd
                    if _lid not in _seen:
                        _seen.add(_lid)
                        selected_location_ids.append(_lid)
        else:
            _hex_id_list = hex_summary["h3_id"].to_list()
            _hex_ids = []
            for _p in _v:
                _cd = _p.get("customdata")
                if _cd:
                    _hex_ids.append(_cd[0] if isinstance(_cd, (list, tuple)) else _cd)
                    continue
                _idx = _p.get("pointIndex")
                if _idx is None:
                    _idx = _p.get("pointNumber")
                if isinstance(_idx, int) and 0 <= _idx < len(_hex_id_list):
                    _hex_ids.append(_hex_id_list[_idx])
            _seen = set()
            for _r in hex_summary.filter(pl.col("h3_id").is_in(_hex_ids)).iter_rows(named=True):
                for _lid in _r["location_ids"]:
                    if _lid not in _seen:
                        _seen.add(_lid)
                        selected_location_ids.append(_lid)
    return (selected_location_ids,)


@app.cell(hide_code=True)
def _(mo):
    map_display_mode = mo.ui.dropdown(
        options={
            "Hex cells": "hex",
            "Exact sites": "points",
        },
        value="Hex cells",
        label="Map display",
        full_width=False,
    )
    map_display_mode
    return (map_display_mode,)


@app.cell(hide_code=True)
def _(mo):
    basemap_picker = mo.ui.dropdown(
        options={
            "Topo": "topo",
            "Imagery": "imagery",
            "Shaded relief": "shaded_relief",
            "Stewardship": "stewardship",
            "OpenStreetMap": "osm",
            "Light": "light",
        },
        value="Topo",
        label="Basemap",
        full_width=False,
    )
    None
    return (basemap_picker,)


@app.cell(hide_code=True)
def _(hex_geojson, hex_summary, locations, map_display_mode, mo):
    # Map. Choose hex cells for protected display or exact site points for precise QA.
    import plotly.graph_objects as go

    if hex_summary.height == 0:
        camera_map = mo.md("_No locations to display._")
    else:
        _ids = hex_summary["h3_id"].to_list()
        _z = hex_summary["species_richness"].to_list()
        _cam = hex_summary["camera_count"].to_list()
        _check = hex_summary["checklists"].to_list()
        _recent = [str(x)[:10] for x in hex_summary["most_recent"].to_list()]
        _rpc = [round(x, 2) for x in hex_summary["richness_per_camera"].to_list()]
        _names_list = [", ".join(ns[:3]) + ("..." if len(ns) > 3 else "")
                       for ns in hex_summary["location_names"].to_list()]
        _customdata = list(zip(_ids, _cam, _check, _recent, _rpc, _names_list))
        _center_lats = hex_summary["center_lat"].to_list()
        _center_lngs = hex_summary["center_lng"].to_list()
        _earth_colors = [
            [0.00, "#f5ead6"],
            [0.20, "#d9c28c"],
            [0.45, "#a7a96b"],
            [0.70, "#8a6f3d"],
            [1.00, "#5f3b24"],
        ]
        _raster_sources = {
            "topo": dict(
                sourcetype="raster",
                source=["https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}"],
                sourceattribution="USGS The National Map",
                below="traces",
            ),
            "imagery": dict(
                sourcetype="raster",
                source=["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
                sourceattribution="Esri World Imagery",
                below="traces",
            ),
            "shaded_relief": dict(
                sourcetype="raster",
                source=["https://basemap.nationalmap.gov/arcgis/rest/services/USGSShadedReliefOnly/MapServer/tile/{z}/{y}/{x}"],
                sourceattribution="USGS 3DEP Shaded Relief",
                below="traces",
            ),
            "shaded_relief_labels": dict(
                sourcetype="raster",
                source=["https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"],
                sourceattribution="Esri World Boundaries and Places",
            ),
            "shaded_relief_roads": dict(
                sourcetype="raster",
                source=["https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"],
                sourceattribution="Esri World Topographic Map",
                opacity=0.55,
                below="traces",
            ),
            "stewardship": dict(
                sourcetype="raster",
                source=["https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"],
                sourceattribution="Esri World Topographic Map",
                below="traces",
            ),
        }
        _basemaps = {
            "Topo": ("white-bg", [_raster_sources["topo"]]),
            "Imagery": ("white-bg", [_raster_sources["imagery"]]),
            "Shaded relief": (
                "white-bg",
                [
                _raster_sources["shaded_relief"],
                _raster_sources["shaded_relief_roads"],
                _raster_sources["shaded_relief_labels"],
                ],
            ),
            "Stewardship": ("white-bg", [_raster_sources["stewardship"]]),
            "OpenStreetMap": ("open-street-map", []),
            "Light": ("carto-positron", []),
        }
        _map_style, _map_layers = _basemaps["Topo"]

        if map_display_mode.value == "points":
            _hex_lookup = {}
            for _r in hex_summary.iter_rows(named=True):
                for _lid in _r["location_ids"]:
                    _hex_lookup[_lid] = _r
            _point_rows = [
                {
                    "location_id": _r["location_id"],
                    "location_name": _r["location_name"],
                    "lat": _r["latitude"],
                    "lon": _r["longitude"],
                    "species_richness": _hex_lookup.get(_r["location_id"], {}).get("species_richness", 0),
                    "checklists": _hex_lookup.get(_r["location_id"], {}).get("checklists", 0),
                    "most_recent": _hex_lookup.get(_r["location_id"], {}).get("most_recent", "\u2014"),
                }
                for _r in locations.iter_rows(named=True)
            ]
            camera_fig = go.Figure(
                go.Scattermap(
                    lat=[r["lat"] for r in _point_rows],
                    lon=[r["lon"] for r in _point_rows],
                    mode="markers",
                    marker=dict(size=14, color="#5f3b24", opacity=0.9),
                    customdata=[
                        (r["location_id"], r["location_name"], r["species_richness"], r["checklists"], r["most_recent"])
                        for r in _point_rows
                    ],
                    hovertemplate=(
                        "<b>%{customdata[1]}</b><br>"
                        "<b>Site</b>: %{customdata[0]}<br>"
                        "<b>Species richness</b>: %{customdata[2]}<br>"
                        "<b>Total observations</b>: %{customdata[3]}<br>"
                        "<b>Most recent</b>: %{customdata[4]}<extra></extra>"
                    ),
                )
            )
        else:
            camera_fig = go.Figure(
                go.Choroplethmap(
                    geojson=hex_geojson,
                    locations=_ids,
                    z=_z,
                    featureidkey="properties.h3_id",
                    colorscale=_earth_colors,
                    marker=dict(line=dict(color="rgba(54,43,25,0.9)", width=1.6), opacity=0.8),
                    selected=dict(marker=dict(opacity=0.95)),
                    unselected=dict(marker=dict(opacity=0.48)),
                    colorbar=dict(title="Species<br>richness", x=0.02, len=0.5, thickness=12),
                    customdata=_customdata,
                    hovertemplate=(
                        "<b>Species richness</b>: %{z}<br>"
                        "<b>Number of cameras</b>: %{customdata[1]}<br>"
                        "<b>Total observations</b>: %{customdata[2]}<br>"
                        "<b>Most recent</b>: %{customdata[3]}<br>"
                        "<b>Richness per camera</b>: %{customdata[4]}<br>"
                        "<i>%{customdata[5]}</i><extra></extra>"
                    ),
                )
            )

        _center_lat = sum(_center_lats) / len(_center_lats)
        _center_lng = sum(_center_lngs) / len(_center_lngs)
        camera_fig.update_layout(
            map=dict(
                style=_map_style,
                layers=_map_layers,
                center=dict(lat=_center_lat, lon=_center_lng),
                zoom=7,
                uirevision="camera-map-view",
            ),
            margin=dict(l=0, r=0, t=0, b=0),
            height=520,
            showlegend=False,
            clickmode="event+select",
            dragmode="pan",
            uirevision="camera-map-view",
            updatemenus=[
                dict(
                    buttons=[
                        dict(
                            label=_label,
                            method="relayout",
                            args=[{"map.style": _style, "map.layers": _layers}],
                        )
                        for _label, (_style, _layers) in _basemaps.items()
                    ],
                    direction="down",
                    showactive=True,
                    x=0.01,
                    xanchor="left",
                    y=0.99,
                    yanchor="top",
                    bgcolor="rgba(255,255,255,0.92)",
                )
            ],
        )
        camera_map = mo.ui.plotly(camera_fig)

    None
    return (camera_map,)


@app.cell(hide_code=True)
def _(camera_map, hex_summary, locations, mo, observations_filtered, pl, selected_location_ids):
    import re as _re

    def _card_row(label, value):
        return (
            "<div style='display:flex; justify-content:space-between; gap:12px; "
            "padding:5px 0; border-bottom:1px solid #eee;'>"
            f"<span style='color:#5b5548;'>{label}</span>"
            f"<strong style='color:#2f2618; text-align:right;'>{value}</strong></div>"
        )

    def _species_list(dep_ids):
        _obs = observations_filtered.filter(pl.col("deployment_id").is_in(dep_ids))
        _pat = _re.compile(r"COMMONNAME:([^\]]+)")
        _counts = {}
        for _row in _obs.select("tags", "media_path").iter_rows(named=True):
            _names = set(_pat.findall(_row["tags"] or ""))
            for _name in _names:
                _counts[_name] = _counts.get(_name, 0) + 1
        return sorted(_counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))

    if selected_location_ids:
        _selected = locations.filter(pl.col("location_id").is_in(selected_location_ids))
        _dep_ids = [d for ds in _selected["deployment_ids"].to_list() for d in ds]
        _species = _species_list(_dep_ids)
        _species_rows = "".join(
            _card_row(name, count)
            for name, count in _species[:12]
        ) or "<div style='color:#777; padding-top:6px;'>No species in current filters.</div>"
        _panel_title = "Selected area"
        _summary = (
            _card_row("Sites", _selected.height)
            + _card_row("Images", int(_selected["image_count"].sum()))
            + _card_row("Tagged images", int(_selected["tagged_image_count"].sum()))
            + _card_row("Species", len(_species))
        )
    else:
        _dep_ids = [d for ds in locations["deployment_ids"].to_list() for d in ds] if locations.height else []
        _species = _species_list(_dep_ids)
        _species_rows = "".join(
            _card_row(name, count)
            for name, count in _species[:10]
        ) or "<div style='color:#777; padding-top:6px;'>No species in current filters.</div>"
        _panel_title = "Current map"
        _summary = (
            _card_row("Map cells", hex_summary.height)
            + _card_row("Sites", locations.height)
            + _card_row("Images", int(locations["image_count"].sum()) if locations.height else 0)
            + _card_row("Species", len(_species))
        )

    map_dashboard = mo.Html(
        "<div style='border:1px solid #ddd4c2; border-radius:8px; padding:12px; "
        "background:#fbfaf6; min-width:220px;'>"
        f"<div style='font-size:18px; font-weight:700; color:#2f2618; margin-bottom:8px;'>{_panel_title}</div>"
        f"{_summary}"
        "<div style='font-size:14px; font-weight:700; color:#2f2618; margin-top:12px;'>Species detected</div>"
        f"{_species_rows}"
        "</div>"
    )
    mo.hstack([camera_map, map_dashboard], widths=[3, 1], align="start")
    return


@app.cell(hide_code=True)
def _(locations, mo, pl, selected_location_ids):
    if not selected_location_ids:
        selection_summary = mo.md("### \u2191 Click, Shift-click, or box-select markers to load the report")
    else:
        _rows = locations.filter(pl.col("location_id").is_in(selected_location_ids))
        _names = ", ".join(_rows["location_name"].to_list())
        _img = int(_rows["image_count"].sum())
        _tag = int(_rows["tagged_image_count"].sum())
        selection_summary = mo.md(
            f"### {len(selected_location_ids)} location(s): {_names}  \n"
            f"{_img} image(s) \u00b7 {_tag} tagged (after filters)"
        )
    selection_summary
    return


@app.cell(hide_code=True)
def _(
    end_date_filter,
    exclude_common,
    locations,
    media_filtered,
    mo,
    observations_filtered,
    pl,
    selected_location_ids,
    start_date_filter,
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

        import re as _re_card
        _pat_card = _re_card.compile(r"COMMONNAME:([^\]]+)")
        _cn_counts = {}
        for _t in _obs_loc["tags"].to_list():
            if not _t:
                continue
            for _m in _pat_card.findall(_t):
                _cn_counts[_m] = _cn_counts.get(_m, 0) + 1
        _common_counts = (
            pl.DataFrame({"common_name": list(_cn_counts.keys()), "images": list(_cn_counts.values())})
            .sort("images", descending=True)
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
        _filter_notes.append(f"date: {start_date_filter.value} \u2192 {end_date_filter.value}")
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
        _dep_locations = pl.DataFrame([
            {
                "deployment_id": d,
                "mountain_range": r["mountain_range"],
                "location_id": r["location_id"],
                "location_name": r["location_name"],
            }
            for r in _rows.iter_rows(named=True)
            for d in r["deployment_ids"]
        ])
        _selected_media = (
            media_filtered
            .filter(pl.col("deployment_id").is_in(_dep_ids))
            .select("media_path", "file_name", "deployment_id", "bucket")
            .unique(subset=["bucket", "media_path"])
            .join(_dep_locations, on="deployment_id", how="left")
        )
        _selected_keys = set(_selected_media.select("bucket", "media_path").iter_rows())
        import re as _re_events
        _common_pat = _re_events.compile(r"COMMONNAME:([^\]]+)")
        _events_by_key = {}
        for _obs in observations_filtered.iter_rows(named=True):
            _key = (_obs["bucket"], _obs["media_path"])
            if _key not in _selected_keys:
                continue
            _name = _obs["scientific_name"] or ""
            _tags = _obs["tags"] or ""
            _names = [_name] if len(_name) >= 3 else _common_pat.findall(_tags)
            _event = _events_by_key.setdefault(
                _key,
                {"bucket": _key[0], "media_path": _key[1], "species": set(), "count": 0, "tags": "", "timestamp": ""},
            )
            _event["species"].update(n for n in _names if n)
            try:
                _event["count"] += int(_obs["count"] or 0)
            except ValueError:
                pass
            if not _event["tags"] and _tags:
                _event["tags"] = _tags
            _ts = _obs["timestamp"] or ""
            if _ts and (not _event["timestamp"] or _ts < _event["timestamp"]):
                _event["timestamp"] = _ts
        _obs_events = pl.DataFrame(
            [
                {
                    "bucket": _event["bucket"],
                    "media_path": _event["media_path"],
                    "scientific_name": ", ".join(sorted(_event["species"])),
                    "count": _event["count"],
                    "tags": _event["tags"],
                    "timestamp": _event["timestamp"],
                }
                for _event in _events_by_key.values()
            ],
            schema={
                "bucket": pl.Utf8,
                "media_path": pl.Utf8,
                "scientific_name": pl.Utf8,
                "count": pl.Int64,
                "tags": pl.Utf8,
                "timestamp": pl.Utf8,
            },
        )
        selected_images_all = (
            _selected_media
            .join(
                _obs_events,
                on=["bucket", "media_path"],
                how="inner",
            )
            .sort("timestamp", descending=False)
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
def _(mo, selected_images_all, selected_location_ids):
    show_image_event_table = mo.ui.checkbox(
        value=True,
        label="Show each selected image file as a table row",
    )
    _species_options = []
    if selected_location_ids and selected_images_all.height > 0:
        _seen = set()
        for _value in selected_images_all["scientific_name"].to_list():
            for _name in [p.strip() for p in (_value or "").split(",") if p.strip()]:
                if _name not in _seen:
                    _seen.add(_name)
                    _species_options.append(_name)
    detection_species_filter = mo.ui.multiselect(
        options=sorted(_species_options),
        value=[],
        label="Detection table species filter (empty = all detected species)",
        full_width=True,
    )
    if selected_location_ids and show_image_event_table.value:
        detection_table_controls = mo.vstack([
            mo.md("**Detection table filters**"),
            show_image_event_table,
            detection_species_filter,
        ])
    elif selected_location_ids:
        detection_table_controls = show_image_event_table
    else:
        detection_table_controls = mo.md("")
    detection_table_controls
    return detection_species_filter, show_image_event_table


@app.cell(hide_code=True)
def _(
    detection_species_filter,
    mo,
    pl,
    selected_images_all,
    selected_location_ids,
    selected_total,
    show_image_event_table,
):
    if not selected_location_ids or not show_image_event_table.value:
        image_event_table = mo.md("")
    elif selected_total == 0:
        image_event_table = mo.md("**No tagged image events match the current filters** at the selected location(s).")
    else:
        _selected_species = set(detection_species_filter.value or [])
        _filtered_images = selected_images_all
        if _selected_species:
            _mask = [
                bool({p.strip() for p in (value or "").split(",") if p.strip()} & _selected_species)
                for value in selected_images_all["scientific_name"].to_list()
            ]
            _filtered_images = selected_images_all.filter(pl.Series("_species_keep", _mask))
        _event_rows = (
            _filtered_images
            .select(
                "timestamp",
                "mountain_range",
                "location_id",
                "location_name",
                "file_name",
                "scientific_name",
                "count",
                "media_path",
                "deployment_id",
            )
            .rename({
                "scientific_name": "species",
                "count": "animal_count",
            })
        )
        if _event_rows.height == 0:
            image_event_table = mo.md("**No image events match the selected species filter.**")
        else:
            image_event_table = mo.ui.table(
                _event_rows,
                show_column_summaries=False,
                show_data_types=False,
                selection=None,
                pagination=True,
            )
    image_event_table
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
