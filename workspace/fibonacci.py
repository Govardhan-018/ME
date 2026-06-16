def fibonacci(n):
    """
    Generate a list of the first n Fibonacci numbers.
    """
    fib_sequence = [0, 1]
    while len(fib_sequence) < n:
        fib_sequence.append(fib_sequence[-1] + fib_sequence[-2])
    return fib_sequence[:n]

if __name__ == "__main__":
    num_terms = int(input("Enter the number of Fibonacci terms to generate: "))
    print(f"The first {num_terms} Fibonacci numbers are: {fibonacci(num_terms)}")