document.addEventListener("DOMContentLoaded", () => {
  const inputA = document.getElementById("Value_A");
  const inputB = document.getElementById("Value_B");
  const submitbtn = document.getElementById("submitbtn");
  const sum = document.getElementById("sum");
  const comp = document.getElementById("comp");
  const spanresult = document.getElementById("result");

  
  [inputA, inputB].forEach(input => {
    input.addEventListener("input", (e) => {
      e.target.value = e.target.value.replace(/[^0-1]/g, "");
    });
  });

  btnEnviar.addEventListener("click", () => {
    const binA = inputA.value;
    const binB = inputB.value;

    const valA = parseInt(binA, 2);
    const valB = parseInt(binB, 2);
    

    const isSum = sum.checked ? 1 : 0;
    const isTwoComp = comp.checked ? 1 : 0;

    spanresult.innerText = "Calculating...";

    fetch(`/api/set-values?valA=${valA}&valB=${valB}&isSum=${sum}&isTwoComp=${comp}`, {
      method: "POST",
    })
    .then(response => response.json())
    .then(data => {
      if (data.status === "success") {
        spanresult.innerText = data.result;
      } else {
        spanresult.innerText = "Error";
      }
    })
    .catch(() => {
      spanResultado.innerText = "Connection error";
    });
  });
});