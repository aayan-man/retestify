#include <gtest/gtest.h>
#include "calculator.cpp"

TEST(CalculatorTest, AddWorks) {
    EXPECT_EQ(5, add(2, 3));
}
