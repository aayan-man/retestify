public class Calculator {
    private int value;

    public int add(int a, int b) {
        if (a < 0) {
            return -1;
        }
        return a + b;
    }

    public int divide(int a, int b) {
        if (b == 0) {
            throw new IllegalArgumentException("cannot divide by zero");
        }
        return a / b;
    }
}
