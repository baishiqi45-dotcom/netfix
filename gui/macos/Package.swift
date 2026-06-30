// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Netfix",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "Netfix", targets: ["Netfix"])
    ],
    targets: [
        .executableTarget(
            name: "Netfix",
            path: "Sources"
        ),
        .testTarget(
            name: "NetfixTests",
            dependencies: ["Netfix"],
            path: "Tests/NetfixTests"
        )
    ]
)
