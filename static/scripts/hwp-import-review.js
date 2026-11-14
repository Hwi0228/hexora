(() => {
  const form = document.querySelector(".import-form");
  const hidden = form?.querySelector('textarea[name="questions_json"]');
  const list = document.getElementById("import-question-list");
  const jsonPreview = document.getElementById("json-result");
  if (!form || !hidden || !list) return;

  let payload;
  try {
    payload = JSON.parse(hidden.value);
  } catch (_error) {
    return;
  }
  const sourceQuestions = Array.isArray(payload) ? payload : payload.questions;
  if (!Array.isArray(sourceQuestions)) return;

  const readCard = (card) => {
    const getField = (name) => card.querySelector('[data-import-field="' + name + '"]');
    const choices = getField("choices");
    return {
      source_number: getField("source_number")?.value.trim() || "",
      question: getField("question")?.innerHTML || "",
      choices: choices
        ? Array.from(choices.querySelectorAll("[data-import-choice]"))
            .map((choice) => choice.innerHTML.trim()).filter(Boolean)
        : [],
      answer: getField("answer")?.innerHTML || "",
      explanation: getField("explanation")?.innerHTML || ""
    };
  };

  const cards = () => Array.from(list.querySelectorAll("[data-import-question]"));
  const originalFor = (question, index) => ({
    source_number: String(question.source_number ?? question.number ?? index + 1),
    question: String(question.question || ""),
    choices: Array.isArray(question.choices) ? question.choices.slice() : [],
    answer: String(question.answer || ""),
    explanation: String(question.explanation || "")
  });

  function questionOriginal(index) {
    return originalFor(sourceQuestions[index] || {}, index);
  }

  cards().forEach((card, index) => {
    const original = questionOriginal(index);
    card.dataset.original = JSON.stringify(original);
    card.dataset.boundaryChanged = "false";
    const originalView = card.querySelector("[data-import-original]");
    if (originalView) originalView.textContent = JSON.stringify(original, null, 2);
  });

  function reindex() {
    cards().forEach((card, index) => {
      card.dataset.index = String(index);
      const checkbox = card.querySelector('input[name="selected_questions"]');
      if (checkbox) {
        checkbox.value = String(index);
        checkbox.setAttribute("aria-label", (index + 1) + "번 문항 DB 등록");
      }
      const heading = card.querySelector(".question-select span");
      if (heading) heading.textContent = (index + 1) + "번 문항";
      const merge = card.querySelector("[data-merge-next]");
      if (merge) merge.disabled = index === cards().length - 1;
    });
  }

  function syncPayload() {
    const updated = cards().map((card, index) => {
      const values = readCard(card);
      const original = JSON.parse(card.dataset.original || "{}");
      const correctedFields = ["source_number", "question", "choices", "answer", "explanation"]
        .filter((field) => JSON.stringify(values[field]) !== JSON.stringify(original[field]));
      if (card.dataset.boundaryChanged === "true") correctedFields.push("question_boundary");
      const question = {
        number: index + 1,
        source_number: values.source_number,
        question: values.question,
        choices: values.choices,
        answer: values.answer,
        explanation: values.explanation
      };
      if (correctedFields.length) {
        question.original = original;
        question.corrected_fields = correctedFields;
      }
      const status = card.querySelector("[data-correction-status]");
      if (status) {
        status.textContent = correctedFields.length ? "수동 보정됨" : "원본";
        status.classList.toggle("is-corrected", correctedFields.length > 0);
      }
      return question;
    });
    if (Array.isArray(payload)) payload = updated;
    else payload.questions = updated;
    hidden.value = JSON.stringify(payload);
    if (jsonPreview) jsonPreview.value = JSON.stringify(payload, null, 2);
  }

  function splitQuestion(card) {
    const editor = card.querySelector('[data-import-field="question"]');
    if (!editor) return;
    let remainder = "";
    const selection = window.getSelection();
    if (selection && selection.rangeCount && editor.contains(selection.anchorNode)) {
      const range = selection.getRangeAt(0).cloneRange();
      range.collapse(true);
      range.setEnd(editor, editor.childNodes.length);
      const fragment = range.extractContents();
      const holder = document.createElement("div");
      holder.append(fragment);
      remainder = holder.innerHTML;
    } else {
      const blocks = Array.from(editor.children);
      if (blocks.length < 2) {
        window.alert("문항을 나눌 위치에 커서를 놓거나 문단을 두 개 이상 작성해 주세요.");
        return;
      }
      const splitAt = Math.ceil(blocks.length / 2);
      remainder = blocks.slice(splitAt).map((node) => node.outerHTML).join("");
      editor.replaceChildren(...blocks.slice(0, splitAt));
    }
    if (!remainder.trim()) {
      window.alert("분리 위치 뒤에 문항 내용이 없습니다.");
      return;
    }

    const nextCard = card.cloneNode(true);
    nextCard.querySelector('[data-import-field="question"]').innerHTML = remainder;
    nextCard.querySelector('[data-import-field="choices"]').replaceChildren();
    nextCard.querySelector('[data-import-field="answer"]').replaceChildren();
    nextCard.querySelector('[data-import-field="explanation"]').replaceChildren();
    const numberInput = nextCard.querySelector('[data-import-field="source_number"]');
    const sourceNumber = card.querySelector('[data-import-field="source_number"]').value.trim();
    numberInput.value = sourceNumber ? sourceNumber + "-b" : "";
    const checkbox = nextCard.querySelector('input[name="selected_questions"]');
    if (checkbox) checkbox.checked = true;
    nextCard.dataset.original = card.dataset.original;
    nextCard.dataset.boundaryChanged = "true";
    card.dataset.boundaryChanged = "true";
    list.insertBefore(nextCard, card.nextElementSibling);
    reindex();
    syncPayload();
  }

  function mergeWithNext(card) {
    const nextCard = card.nextElementSibling;
    if (!nextCard || !nextCard.matches("[data-import-question]")) return;
    const getField = (element, name) => element.querySelector('[data-import-field="' + name + '"]');
    const currentQuestion = getField(card, "question");
    const nextQuestion = getField(nextCard, "question");
    currentQuestion.insertAdjacentHTML("beforeend", "<p><br></p>" + nextQuestion.innerHTML);
    const currentChoices = getField(card, "choices");
    const nextChoices = getField(nextCard, "choices");
    Array.from(nextChoices.children).forEach((choice) => currentChoices.append(choice.cloneNode(true)));

    for (const field of ["answer", "explanation"]) {
      const current = getField(card, field);
      const next = getField(nextCard, field);
      if (!current.innerHTML.trim()) current.innerHTML = next.innerHTML;
      else if (next.innerHTML.trim()) current.insertAdjacentHTML("beforeend", "<p><br></p>" + next.innerHTML);
    }

    const leftOriginal = JSON.parse(card.dataset.original || "{}");
    const rightOriginal = JSON.parse(nextCard.dataset.original || "{}");
    card.dataset.original = JSON.stringify({
      source_number: [leftOriginal.source_number, rightOriginal.source_number].filter(Boolean).join(", "),
      question: [leftOriginal.question, rightOriginal.question].filter(Boolean).join("\n"),
      choices: [...(leftOriginal.choices || []), ...(rightOriginal.choices || [])],
      answer: [leftOriginal.answer, rightOriginal.answer].filter(Boolean).join("\n"),
      explanation: [leftOriginal.explanation, rightOriginal.explanation].filter(Boolean).join("\n")
    });
    card.dataset.boundaryChanged = "true";
    nextCard.remove();
    reindex();
    syncPayload();
  }

  list.addEventListener("click", (event) => {
    const split = event.target.closest("[data-split-question]");
    if (split) {
      splitQuestion(split.closest("[data-import-question]"));
      return;
    }
    const merge = event.target.closest("[data-merge-next]");
    if (merge) mergeWithNext(merge.closest("[data-import-question]"));
  });

  form.addEventListener("input", syncPayload);
  form.addEventListener("change", syncPayload);
  form.addEventListener("submit", (event) => {
    syncPayload();
    const acknowledgement = form.querySelector('input[name="warnings_acknowledged"]');
    if (acknowledgement && !acknowledgement.checked) {
      event.preventDefault();
      acknowledgement.focus();
    }
  });
  reindex();
  syncPayload();
})();
