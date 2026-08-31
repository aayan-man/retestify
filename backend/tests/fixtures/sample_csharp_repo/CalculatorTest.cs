using Xunit;

public class CalculatorTest
{
    [Fact]
    public void TestAdd()
    {
        var calc = new Calculator();
        Assert.Equal(5, calc.Add(2, 3));
    }
}
