(() => {
  const form = document.querySelector(".upload-form");
  const fileInput = form?.querySelector('input[type="file"]');
  const submitButton = form?.querySelector('button[type="submit"]');

  form?.addEventListener("submit", () => {
    if (!fileInput?.files?.length) return;
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "문서 분석 중…";
    }
  });

  const downloadButton = document.getElementById("download-json");
  const jsonOutput = document.getElementById("json-result");
  downloadButton?.addEventListener("click", () => {
    if (!jsonOutput) return;
    const blob = new Blob([jsonOutput.value], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "questions.json";
    link.click();
    URL.revokeObjectURL(url);
  });
})();
