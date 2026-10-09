import argparse


def main():
    parser = argparse.ArgumentParser(description="Count text supplied as an argument")
    parser.add_argument("text")
    args = parser.parse_args()
    counts = {"lines": len(args.text.splitlines()),
              "words": len(args.text.split()),
              "characters": len(args.text)}
    for name, count in counts.items():
        print(f"{name}: {count}")


if __name__ == "__main__":
    main()
