use image::ImageError;
use ocrs::{ImageSource, OcrEngine as OcrsEngine, OcrEngineParams};
use pyo3::exceptions::{PyOSError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use rten::Model;
use std::path::Path;

#[pyclass]
#[derive(Clone, Debug)]
pub struct OcrResult {
    #[pyo3(get)]
    pub text: String,
}

impl OcrResult {
    fn new(text: String) -> Self {
        Self { text }
    }
}

#[pymethods]
impl OcrResult {
    #[new]
    fn py_new(text: String) -> Self {
        Self::new(text)
    }

    fn __repr__(&self) -> String {
        format!("OcrResult(text={:?})", self.text)
    }
}

#[pyclass]
pub struct OcrEngine {
    engine: OcrsEngine,
}

impl OcrEngine {
    fn run_ocr(&self, image: image::DynamicImage) -> PyResult<OcrResult> {
        let image = image.into_rgb8();
        let source = ImageSource::from_bytes(image.as_raw(), image.dimensions())
            .map_err(|error| PyValueError::new_err(error.to_string()))?;
        let input = self
            .engine
            .prepare_input(source)
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
        let text = self
            .engine
            .get_text(&input)
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;

        Ok(OcrResult::new(text.trim().to_string()))
    }
}

#[pymethods]
impl OcrEngine {
    #[new]
    fn new(detection_model_path: &str, recognition_model_path: &str) -> PyResult<Self> {
        let detection_model = Model::load_file(detection_model_path)
            .map_err(|error| PyOSError::new_err(error.to_string()))?;
        let recognition_model = Model::load_file(recognition_model_path)
            .map_err(|error| PyOSError::new_err(error.to_string()))?;
        let engine = OcrsEngine::new(OcrEngineParams {
            detection_model: Some(detection_model),
            recognition_model: Some(recognition_model),
            ..Default::default()
        })
        .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;

        Ok(Self { engine })
    }

    /// Run OCR on an image file and return an OcrResult.
    fn ocr_file(&self, path: &str) -> PyResult<OcrResult> {
        let image = image::open(Path::new(path)).map_err(image_error_to_pyerr)?;
        self.run_ocr(image)
    }

    /// Run OCR on encoded image bytes. The format is detected from the bytes.
    fn ocr_bytes(&self, data: &[u8]) -> PyResult<OcrResult> {
        let image = image::load_from_memory(data).map_err(image_error_to_pyerr)?;
        self.run_ocr(image)
    }

    /// Run OCR on multiple image files sequentially.
    fn ocr_batch(&self, paths: Vec<String>) -> PyResult<Vec<OcrResult>> {
        paths.iter().map(|path| self.ocr_file(path)).collect()
    }
}

fn image_error_to_pyerr(error: ImageError) -> PyErr {
    match error {
        ImageError::IoError(error) => PyOSError::new_err(error.to_string()),
        error => PyValueError::new_err(error.to_string()),
    }
}

#[pymodule]
fn selfpdf_ocr(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<OcrEngine>()?;
    module.add_class::<OcrResult>()?;
    Ok(())
}
