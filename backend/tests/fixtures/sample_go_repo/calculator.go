package calc

func Add(a, b int) int {
	if a < 0 {
		return -1
	}
	return a + b
}

type Calculator struct {
	Value int
}

func (c *Calculator) Multiply(a int) int {
	return c.Value * a
}
