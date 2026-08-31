const { add, divide } = require("./calculator");

test("add works", () => {
  expect(add(2, 3)).toBe(5);
});

test("divide works", () => {
  expect(divide(6, 3)).toBe(2);
});

it("divide throws on zero", () => {
  expect(() => divide(1, 0)).toThrow();
});
