(() => {
  const source = document.getElementById("segment-source");
  const preview = document.getElementById("segment-preview");
  const count = document.getElementById("segment-count");
  const form = document.getElementById("segment-import-form");
  const payloadField = document.getElementById("questions-json");
  if (!source || !preview || !form || !payloadField) return;

  const rows = [...source.querySelectorAll(".segment-block")];
  const getBoundaries = () => rows
    .filter((row) => row.querySelector(".question-boundary")?.checked)
    .map((row) => Number(row.dataset.index))
    .sort((a, b) => a - b);
  const getAnswerStart = () => {
    const row = rows.find((item) => item.querySelector(".answer-boundary")?.checked);
    return row ? Number(row.dataset.index) : null;
  };

  function update() {
    const previousSelection = new Map(
      [...preview.querySelectorAll(".preview-select")].map((input) => [input.value, input.checked])
    );
    rows.forEach((row) => {
      const boundary = row.querySelector(".question-boundary");
      const number = row.querySelector(".question-number");
      const active = Boolean(boundary?.checked);
      if (number) number.disabled = !active;
      row.classList.toggle("is-question-start", active);
    });

    const answerStart = getAnswerStart();
    const boundaries = getBoundaries().filter((index) => answerStart === null || index < answerStart);
    const items = [];
    boundaries.forEach((start, position) => {
      const next = boundaries[position + 1];
      const end = Math.min(next === undefined ? rows.length : next, answerStart === null ? rows.length : answerStart) - 1;
      const text = rows
        .filter((row) => {
          const index = Number(row.dataset.index);
          return index >= start && index <= end;
        })
        .map((row) => row.querySelector(".segment-text")?.textContent.trim() || "")
        .filter(Boolean)
        .join("\n");
      const row = rows.find((item) => Number(item.dataset.index) === start);
      const enteredNumber = row?.querySelector(".question-number")?.value.trim() || "";
      items.push({
        number: enteredNumber || String(position + 1),
        source_number: enteredNumber || String(position + 1),
        question: text,
        choices: [],
        answer: "",
        explanation: ""
      });
    });

    preview.replaceChildren();
    items.forEach((item, index) => {
      const card = document.createElement("article");
      card.className = "segment-preview-item";
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.className = "preview-select";
      checkbox.value = String(index);
      checkbox.checked = previousSelection.has(String(index)) ? previousSelection.get(String(index)) : true;
      label.append(checkbox, document.createTextNode(" " + item.number + "번 문항 등록"));
      const body = document.createElement("p");
      body.textContent = item.question || "(선택한 구역에 텍스트가 없습니다.)";
      card.append(label, body);
      preview.append(card);
    });
    if (count) count.textContent = "현재 " + items.length + "개 문항 구역 · 정답 영역 시작: " + (answerStart === null ? "지정 안 됨" : "블록 " + (answerStart + 1));
    form.dataset.questionCount = String(items.length);
    form._segmentedQuestions = items;
  }

  source.addEventListener("change", (event) => {
    if (event.target.matches(".answer-boundary") && event.target.checked) {
      rows.forEach((row) => {
        const checkbox = row.querySelector(".answer-boundary");
        if (checkbox !== event.target) checkbox.checked = false;
      });
    }
    update();
  });
  source.addEventListener("input", (event) => {
    if (event.target.matches(".question-number")) update();
  });

  form.addEventListener("submit", (event) => {
    const questions = form._segmentedQuestions || [];
    const selected = [...preview.querySelectorAll(".preview-select:checked")]
      .map((input) => Number(input.value));
    if (!questions.length) {
      event.preventDefault();
      window.alert("문항 시작 지점을 하나 이상 지정해 주세요.");
      return;
    }
    if (!selected.length) {
      event.preventDefault();
      window.alert("DB에 등록할 문항을 하나 이상 선택해 주세요.");
      return;
    }
    payloadField.value = JSON.stringify({ questions });
    form.querySelectorAll('input[name="selected_questions"]').forEach((input) => input.remove());
    selected.forEach((index) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "selected_questions";
      input.value = String(index);
      form.append(input);
    });
  });

  update();
})();
