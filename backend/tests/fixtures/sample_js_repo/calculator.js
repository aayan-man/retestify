function add(a, b) {
  return a + b;
}

function divide(a, b) {
  if (b === 0) {
    throw new Error("cannot divide by zero");
  }
  return a / b;
}

class Calculator {
  constructor(start = 0) {
    this.value = start;
  }

  add(n) {
    this.value += n;
    return this.value;
  }
}

module.exports = { add, divide, Calculator };
