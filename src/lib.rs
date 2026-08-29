//! fitfast: fast Garmin FIT parsing for Python, backed by the rustyfit crate.
//!
//! Semantics follow the official Garmin FIT SDKs where it matters:
//! - Fields whose value is the FIT "invalid" sentinel for their base type are
//!   omitted from `parse()` output and become NaN in `records()` columns.
//! - Profile scale/offset are applied to integer-typed fields.
//! - `date_time`/`local_date_time` values are converted from the FIT epoch
//!   (1989-12-31T00:00:00Z) to Unix timestamps.
//! - Developer fields are decoded using their `field_description` messages.
//!
//! Known limitations (v0.1): dynamic sub-fields are not resolved (the main
//! field's name/type is used), and component expansion follows rustyfit's
//! decoder (expanded fields such as `enhanced_speed` appear as regular fields).

mod enum_names;

use std::collections::HashMap;

use numpy::IntoPyArray;
use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDateTime, PyDict, PyList, PyString, PyTzInfo};
use rustyfit::profile::typedef::{FitBaseType, MesgNum};
use rustyfit::profile::{lookup, ProfileType};
use rustyfit::proto::{DeveloperField, Field, Message, Value};
use rustyfit::Decoder;

create_exception!(
    fitfast,
    FitDecodeError,
    PyValueError,
    "Raised when the input is not a valid FIT file or fails to decode."
);

/// Seconds between the Unix epoch and the FIT epoch (1989-12-31T00:00:00Z).
const FIT_EPOCH_OFFSET: i64 = 631_065_600;
/// Multiplier converting semicircles to degrees.
const SEMICIRCLES_TO_DEGREES: f64 = 180.0 / 2_147_483_648.0;

// ---------------------------------------------------------------------------
// Decoding
// ---------------------------------------------------------------------------

fn decode_all(data: &[u8]) -> PyResult<Vec<Message>> {
    if data.is_empty() {
        return Err(FitDecodeError::new_err("input is empty, not a FIT file"));
    }
    let mut dec = Decoder::new();
    let mut reader: &[u8] = data;
    let mut messages: Vec<Message> = Vec::new();
    let mut sequences = 0usize;
    loop {
        match dec.decode(&mut reader) {
            Ok(Some(fit)) => {
                sequences += 1;
                if messages.is_empty() {
                    messages = fit.messages;
                } else {
                    messages.extend(fit.messages);
                }
            }
            Ok(None) => break,
            Err(e) => {
                return Err(FitDecodeError::new_err(format!(
                    "FIT decode error{}: {e}",
                    if sequences > 0 {
                        format!(" (after {sequences} valid FIT sequence(s))")
                    } else {
                        String::new()
                    }
                )))
            }
        }
    }
    if sequences == 0 {
        return Err(FitDecodeError::new_err("no FIT data found in input"));
    }
    Ok(messages)
}

// ---------------------------------------------------------------------------
// FIT invalid-sentinel semantics
// ---------------------------------------------------------------------------

fn is_invalid(base_type: FitBaseType, v: &Value) -> bool {
    let z8 = base_type == FitBaseType::UINT8Z;
    let z16 = base_type == FitBaseType::UINT16Z;
    let z32 = base_type == FitBaseType::UINT32Z;
    let z64 = base_type == FitBaseType::UINT64Z;
    match v {
        Value::Invalid => true,
        Value::Int8(x) => *x == i8::MAX,
        Value::Uint8(x) => {
            if z8 {
                *x == 0
            } else {
                *x == u8::MAX
            }
        }
        Value::Int16(x) => *x == i16::MAX,
        Value::Uint16(x) => {
            if z16 {
                *x == 0
            } else {
                *x == u16::MAX
            }
        }
        Value::Int32(x) => *x == i32::MAX,
        Value::Uint32(x) => {
            if z32 {
                *x == 0
            } else {
                *x == u32::MAX
            }
        }
        Value::Int64(x) => *x == i64::MAX,
        Value::Uint64(x) => {
            if z64 {
                *x == 0
            } else {
                *x == u64::MAX
            }
        }
        Value::Float32(x) => x.is_nan(),
        Value::Float64(x) => x.is_nan(),
        Value::String(s) => s.is_empty(),
        Value::VecInt8(xs) => xs.iter().all(|&x| x == i8::MAX),
        Value::VecUint8(xs) => xs.iter().all(|&x| if z8 { x == 0 } else { x == u8::MAX }),
        Value::VecInt16(xs) => xs.iter().all(|&x| x == i16::MAX),
        Value::VecUint16(xs) => xs.iter().all(|&x| if z16 { x == 0 } else { x == u16::MAX }),
        Value::VecInt32(xs) => xs.iter().all(|&x| x == i32::MAX),
        Value::VecUint32(xs) => xs.iter().all(|&x| if z32 { x == 0 } else { x == u32::MAX }),
        Value::VecInt64(xs) => xs.iter().all(|&x| x == i64::MAX),
        Value::VecUint64(xs) => xs.iter().all(|&x| if z64 { x == 0 } else { x == u64::MAX }),
        Value::VecFloat32(xs) => xs.iter().all(|x| x.is_nan()),
        Value::VecFloat64(xs) => xs.iter().all(|x| x.is_nan()),
        Value::VecString(xs) => xs.iter().all(|s| s.is_empty()),
    }
}

fn scalar_f64(v: &Value) -> Option<f64> {
    match v {
        Value::Int8(x) => Some(*x as f64),
        Value::Uint8(x) => Some(*x as f64),
        Value::Int16(x) => Some(*x as f64),
        Value::Uint16(x) => Some(*x as f64),
        Value::Int32(x) => Some(*x as f64),
        Value::Uint32(x) => Some(*x as f64),
        Value::Int64(x) => Some(*x as f64),
        Value::Uint64(x) => Some(*x as f64),
        Value::Float32(x) => Some(*x as f64),
        Value::Float64(x) => Some(*x),
        _ => None,
    }
}

fn scalar_int(v: &Value) -> Option<i128> {
    match v {
        Value::Int8(x) => Some(*x as i128),
        Value::Uint8(x) => Some(*x as i128),
        Value::Int16(x) => Some(*x as i128),
        Value::Uint16(x) => Some(*x as i128),
        Value::Int32(x) => Some(*x as i128),
        Value::Uint32(x) => Some(*x as i128),
        Value::Int64(x) => Some(*x as i128),
        Value::Uint64(x) => Some(*x as i128),
        _ => None,
    }
}

fn is_integer_value(v: &Value) -> bool {
    scalar_int(v).is_some()
        || matches!(
            v,
            Value::VecInt8(_)
                | Value::VecUint8(_)
                | Value::VecInt16(_)
                | Value::VecUint16(_)
                | Value::VecInt32(_)
                | Value::VecUint32(_)
                | Value::VecInt64(_)
                | Value::VecUint64(_)
        )
}

// ---------------------------------------------------------------------------
// Developer field descriptions
// ---------------------------------------------------------------------------

struct DevFieldInfo {
    name: String,
    scale: Option<f64>,
    offset: f64,
    base_type: Option<FitBaseType>,
}

/// Fallback base type for a decoded value when no `field_description` is
/// available: the non-Z type matching the value's representation.
fn default_base_type(v: &Value) -> FitBaseType {
    match v {
        Value::Int8(_) | Value::VecInt8(_) => FitBaseType::SINT8,
        Value::Uint8(_) | Value::VecUint8(_) => FitBaseType::UINT8,
        Value::Int16(_) | Value::VecInt16(_) => FitBaseType::SINT16,
        Value::Uint16(_) | Value::VecUint16(_) => FitBaseType::UINT16,
        Value::Int32(_) | Value::VecInt32(_) => FitBaseType::SINT32,
        Value::Uint32(_) | Value::VecUint32(_) => FitBaseType::UINT32,
        Value::Int64(_) | Value::VecInt64(_) => FitBaseType::SINT64,
        Value::Uint64(_) | Value::VecUint64(_) => FitBaseType::UINT64,
        Value::Float32(_) | Value::VecFloat32(_) => FitBaseType::FLOAT32,
        Value::Float64(_) | Value::VecFloat64(_) => FitBaseType::FLOAT64,
        _ => FitBaseType::STRING,
    }
}

fn dev_field_is_invalid(f: &DeveloperField, reg: &HashMap<(u8, u8), DevFieldInfo>) -> bool {
    let base_type = reg
        .get(&(f.developer_data_index, f.num))
        .and_then(|i| i.base_type)
        .unwrap_or_else(|| default_base_type(&f.value));
    is_invalid(base_type, &f.value)
}

/// Collect `field_description` messages into a
/// (developer_data_index, field_definition_number) -> info map.
fn dev_field_registry(messages: &[Message]) -> HashMap<(u8, u8), DevFieldInfo> {
    // field_description field numbers, per the FIT profile
    const DEVELOPER_DATA_INDEX: u8 = 0;
    const FIELD_DEFINITION_NUMBER: u8 = 1;
    const FIT_BASE_TYPE_ID: u8 = 2;
    const FIELD_NAME: u8 = 3;
    const SCALE: u8 = 6;
    const OFFSET: u8 = 7;

    let mut reg = HashMap::new();
    for m in messages {
        if m.num != MesgNum::FIELD_DESCRIPTION {
            continue;
        }
        let mut ddi: Option<u8> = None;
        let mut fdn: Option<u8> = None;
        let mut name: Option<String> = None;
        let mut scale: Option<f64> = None;
        let mut offset: f64 = 0.0;
        let mut base_type: Option<FitBaseType> = None;
        for f in &m.fields {
            if is_invalid(f.base_type, &f.value) {
                continue;
            }
            match f.num {
                DEVELOPER_DATA_INDEX => ddi = scalar_int(&f.value).map(|v| v as u8),
                FIELD_DEFINITION_NUMBER => fdn = scalar_int(&f.value).map(|v| v as u8),
                FIT_BASE_TYPE_ID => {
                    base_type = scalar_int(&f.value).map(|v| FitBaseType(v as u8));
                }
                FIELD_NAME => {
                    name = match &f.value {
                        Value::String(s) => Some(s.clone()),
                        Value::VecString(xs) => xs.first().cloned(),
                        _ => None,
                    }
                }
                SCALE => {
                    scale = scalar_f64(&f.value).filter(|&s| s != 0.0);
                }
                OFFSET => offset = scalar_f64(&f.value).unwrap_or(0.0),
                _ => {}
            }
        }
        if let (Some(ddi), Some(fdn)) = (ddi, fdn) {
            reg.insert(
                (ddi, fdn),
                DevFieldInfo {
                    name: name.unwrap_or_else(|| format!("dev_{ddi}_{fdn}")),
                    scale,
                    offset,
                    base_type,
                },
            );
        }
    }
    reg
}

fn dev_field_scaled(f: &DeveloperField, reg: &HashMap<(u8, u8), DevFieldInfo>) -> Option<f64> {
    let raw = scalar_f64(&f.value)?;
    match reg.get(&(f.developer_data_index, f.num)) {
        Some(info) => match info.scale {
            Some(s) => Some(raw / s - info.offset),
            None => Some(raw),
        },
        None => Some(raw),
    }
}

fn dev_field_name(f: &DeveloperField, reg: &HashMap<(u8, u8), DevFieldInfo>) -> String {
    match reg.get(&(f.developer_data_index, f.num)) {
        Some(info) => info.name.clone(),
        None => format!("dev_{}_{}", f.developer_data_index, f.num),
    }
}

// ---------------------------------------------------------------------------
// Message grouping (display name per global message number, computed once)
// ---------------------------------------------------------------------------

fn mesg_name(num: MesgNum) -> String {
    let s = num.to_string();
    if s.starts_with("MesgNum(") {
        format!("unknown_{}", num.0)
    } else {
        s
    }
}

/// Group message indices by global message number, preserving first-seen order.
fn group_by_num(messages: &[Message]) -> Vec<(MesgNum, Vec<usize>)> {
    let mut order: Vec<(MesgNum, Vec<usize>)> = Vec::new();
    let mut idx: HashMap<u16, usize> = HashMap::new();
    for (i, m) in messages.iter().enumerate() {
        match idx.get(&m.num.0) {
            Some(&g) => order[g].1.push(i),
            None => {
                idx.insert(m.num.0, order.len());
                order.push((m.num, vec![i]));
            }
        }
    }
    order
}

// ---------------------------------------------------------------------------
// count / mesg_counts
// ---------------------------------------------------------------------------

#[pyfunction]
fn count(py: Python<'_>, data: &[u8]) -> PyResult<(usize, usize)> {
    py.detach(|| {
        let messages = decode_all(data)?;
        let nf = messages
            .iter()
            .map(|m| m.fields.len() + m.developer_fields.len())
            .sum();
        Ok((messages.len(), nf))
    })
}

#[pyfunction]
fn mesg_counts<'py>(py: Python<'py>, data: &[u8]) -> PyResult<Bound<'py, PyDict>> {
    let groups = py.detach(|| {
        let messages = decode_all(data)?;
        Ok::<_, PyErr>(
            group_by_num(&messages)
                .into_iter()
                .map(|(num, idxs)| (mesg_name(num), idxs.len()))
                .collect::<Vec<_>>(),
        )
    })?;
    let out = PyDict::new(py);
    for (name, n) in groups {
        out.set_item(name, n)?;
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// records: columnar output
// ---------------------------------------------------------------------------

#[derive(Default)]
struct Columns {
    names: Vec<String>,
    data: Vec<Vec<f64>>,
    index: HashMap<String, usize>,
}

impl Columns {
    fn set(&mut self, name: &str, row: usize, value: f64) {
        let col = match self.index.get(name) {
            Some(&c) => c,
            None => {
                self.index.insert(name.to_string(), self.data.len());
                self.names.push(name.to_string());
                self.data.push(vec![f64::NAN; row]);
                self.data.len() - 1
            }
        };
        let col = &mut self.data[col];
        if col.len() < row {
            col.resize(row, f64::NAN);
        }
        if col.len() == row {
            col.push(value);
        } else {
            col[row] = value; // duplicate field in one message: last wins
        }
    }

    fn finish(&mut self, rows: usize) {
        for col in &mut self.data {
            col.resize(rows, f64::NAN);
        }
    }
}

/// Convert one profile field's raw scalar to its columnar f64 value.
fn profile_value_f64(fr: &lookup::FieldReference, f: &Field, raw: f64, degrees: bool) -> f64 {
    match fr.profile_type {
        ProfileType::DateTime | ProfileType::LocalDateTime => raw + FIT_EPOCH_OFFSET as f64,
        _ => {
            if degrees && matches!(fr.units, lookup::Unit::Semicircle) {
                raw * SEMICIRCLES_TO_DEGREES
            } else if is_integer_value(&f.value) {
                raw / fr.scale - fr.offset
            } else {
                raw
            }
        }
    }
}

#[pyfunction]
#[pyo3(signature = (data, message="record", *, degrees=true))]
fn records<'py>(
    py: Python<'py>,
    data: &[u8],
    message: &str,
    degrees: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let mut cols = py.detach(|| {
        let messages = decode_all(data)?;
        let reg = dev_field_registry(&messages);
        let groups = group_by_num(&messages);
        let target = groups
            .into_iter()
            .find(|(num, _)| mesg_name(*num) == message);

        let mut cols = Columns::default();
        let mut rows = 0usize;
        // per-call caches so the row loop stays allocation-free
        let mut unknown_names: HashMap<u8, String> = HashMap::new();
        let mut dev_names: HashMap<(u8, u8), String> = HashMap::new();
        if let Some((_, idxs)) = target {
            for &i in &idxs {
                let m = &messages[i];
                let row = rows;
                for f in &m.fields {
                    if is_invalid(f.base_type, &f.value) {
                        continue;
                    }
                    let Some(raw) = scalar_f64(&f.value) else {
                        continue;
                    };
                    match lookup::field_reference(m.num, f.num) {
                        Some(fr) => {
                            cols.set(
                                fr.name.as_str(),
                                row,
                                profile_value_f64(&fr, f, raw, degrees),
                            );
                        }
                        None => {
                            let name = unknown_names
                                .entry(f.num)
                                .or_insert_with(|| format!("unknown_{}", f.num));
                            cols.set(name, row, raw);
                        }
                    }
                }
                for f in &m.developer_fields {
                    if dev_field_is_invalid(f, &reg) {
                        continue;
                    }
                    if let Some(v) = dev_field_scaled(f, &reg) {
                        let name = dev_names
                            .entry((f.developer_data_index, f.num))
                            .or_insert_with(|| dev_field_name(f, &reg));
                        cols.set(name, row, v);
                    }
                }
                rows += 1;
            }
        }
        cols.finish(rows);
        Ok::<_, PyErr>(cols)
    })?;

    let out = PyDict::new(py);
    for (name, col) in cols.names.iter().zip(cols.data.drain(..)) {
        out.set_item(name, col.into_pyarray(py))?;
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// parse: dict-of-dicts output
// ---------------------------------------------------------------------------

struct ParseOpts {
    enum_names: bool,
    datetimes: bool,
}

fn timestamp_to_py<'py>(py: Python<'py>, unix: i64, opts: &ParseOpts) -> PyResult<Py<PyAny>> {
    if opts.datetimes {
        let utc = PyTzInfo::utc(py)?;
        Ok(PyDateTime::from_timestamp(py, unix as f64, Some(&utc))?
            .into_any()
            .unbind())
    } else {
        Ok(unix.into_pyobject(py)?.into_any().unbind())
    }
}

fn scaled_to_py<'py>(py: Python<'py>, v: &Value, scale: f64, offset: f64) -> PyResult<Py<PyAny>> {
    let scaled = scale != 1.0 || offset != 0.0;
    macro_rules! num {
        ($x:expr) => {
            if scaled && is_integer_value(v) {
                Ok((($x as f64) / scale - offset)
                    .into_pyobject(py)?
                    .into_any()
                    .unbind())
            } else {
                Ok($x.into_pyobject(py)?.into_any().unbind())
            }
        };
    }
    macro_rules! vec_num {
        ($xs:expr) => {
            if scaled {
                Ok($xs
                    .iter()
                    .map(|&x| (x as f64) / scale - offset)
                    .collect::<Vec<f64>>()
                    .into_pyobject(py)?
                    .into_any()
                    .unbind())
            } else {
                Ok($xs.clone().into_pyobject(py)?.into_any().unbind())
            }
        };
    }
    match v {
        Value::Invalid => Ok(py.None()),
        Value::Int8(x) => num!(*x),
        Value::Uint8(x) => num!(*x),
        Value::Int16(x) => num!(*x),
        Value::Uint16(x) => num!(*x),
        Value::Int32(x) => num!(*x),
        Value::Uint32(x) => num!(*x),
        Value::Int64(x) => num!(*x),
        Value::Uint64(x) => num!(*x),
        Value::Float32(x) => num!(*x),
        Value::Float64(x) => num!(*x),
        Value::String(s) => Ok(PyString::new(py, s).into_any().unbind()),
        Value::VecInt8(xs) => vec_num!(xs),
        Value::VecUint8(xs) => vec_num!(xs),
        Value::VecInt16(xs) => vec_num!(xs),
        Value::VecUint16(xs) => vec_num!(xs),
        Value::VecInt32(xs) => vec_num!(xs),
        Value::VecUint32(xs) => vec_num!(xs),
        Value::VecInt64(xs) => vec_num!(xs),
        Value::VecUint64(xs) => vec_num!(xs),
        Value::VecFloat32(xs) => Ok(xs.clone().into_pyobject(py)?.into_any().unbind()),
        Value::VecFloat64(xs) => Ok(xs.clone().into_pyobject(py)?.into_any().unbind()),
        // A single NUL-terminated string in a string-typed field is a scalar
        // (the profile's array size is a byte budget); keep real multi-string
        // payloads as lists, matching the official SDK.
        Value::VecString(xs) if xs.len() == 1 => Ok(PyString::new(py, &xs[0]).into_any().unbind()),
        Value::VecString(xs) => Ok(xs.clone().into_pyobject(py)?.into_any().unbind()),
    }
}

fn field_to_py<'py>(
    py: Python<'py>,
    mesg_num: MesgNum,
    f: &Field,
    opts: &ParseOpts,
) -> PyResult<Option<(Py<PyAny>, Py<PyAny>)>> {
    if is_invalid(f.base_type, &f.value) {
        return Ok(None);
    }
    match lookup::field_reference(mesg_num, f.num) {
        Some(fr) => {
            // dict keys repeat for every message of a kind: intern them
            let key = PyString::intern(py, fr.name.as_str()).into_any().unbind();
            let value = match fr.profile_type {
                ProfileType::DateTime | ProfileType::LocalDateTime => match scalar_int(&f.value) {
                    Some(v) => timestamp_to_py(py, v as i64 + FIT_EPOCH_OFFSET, opts)?,
                    None => scaled_to_py(py, &f.value, fr.scale, fr.offset)?,
                },
                pt => {
                    let named = if opts.enum_names && fr.scale == 1.0 && fr.offset == 0.0 {
                        scalar_int(&f.value).and_then(|v| enum_names::enum_value_name(pt, v))
                    } else {
                        None
                    };
                    match named {
                        // enum names form a small closed set: intern them
                        Some(name) => PyString::intern(py, &name).into_any().unbind(),
                        None => scaled_to_py(py, &f.value, fr.scale, fr.offset)?,
                    }
                }
            };
            Ok(Some((key, value)))
        }
        None => {
            let key = f.num.into_pyobject(py)?.into_any().unbind();
            let value = scaled_to_py(py, &f.value, 1.0, 0.0)?;
            Ok(Some((key, value)))
        }
    }
}

#[pyfunction]
#[pyo3(signature = (data, *, enum_names=true, datetimes=false))]
fn parse<'py>(
    py: Python<'py>,
    data: &[u8],
    enum_names: bool,
    datetimes: bool,
) -> PyResult<Bound<'py, PyDict>> {
    let opts = ParseOpts {
        enum_names,
        datetimes,
    };
    let messages = py.detach(|| decode_all(data))?;
    let reg = dev_field_registry(&messages);
    let groups = group_by_num(&messages);

    let out = PyDict::new(py);
    for (num, idxs) in groups {
        let list = PyList::empty(py);
        for &i in &idxs {
            let m = &messages[i];
            let d = PyDict::new(py);
            for f in &m.fields {
                if let Some((key, value)) = field_to_py(py, m.num, f, &opts)? {
                    d.set_item(key, value)?;
                }
            }
            for f in &m.developer_fields {
                if dev_field_is_invalid(f, &reg) {
                    continue;
                }
                let info = reg.get(&(f.developer_data_index, f.num));
                let (scale, offset) = match info {
                    Some(i) => (i.scale.unwrap_or(1.0), i.offset),
                    None => (1.0, 0.0),
                };
                let key = match info {
                    Some(i) => PyString::intern(py, &i.name),
                    None => PyString::intern(py, &dev_field_name(f, &reg)),
                };
                d.set_item(key, scaled_to_py(py, &f.value, scale, offset)?)?;
            }
            list.append(d)?;
        }
        out.set_item(mesg_name(num), list)?;
    }
    Ok(out)
}

// ---------------------------------------------------------------------------

#[pymodule]
fn _native(py: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(count, m)?)?;
    m.add_function(wrap_pyfunction!(mesg_counts, m)?)?;
    m.add_function(wrap_pyfunction!(records, m)?)?;
    m.add_function(wrap_pyfunction!(parse, m)?)?;
    m.add("FitDecodeError", py.get_type::<FitDecodeError>())?;
    m.add("__profile_version__", rustyfit::profile::PROFILE_VERSION)?;
    Ok(())
}
