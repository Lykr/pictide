// Native desktop entry; the bundled Python service still owns all application logic.
import AppKit
import Foundation
import Darwin

let engine = URL(fileURLWithPath: CommandLine.arguments[0]).deletingLastPathComponent()
    .appendingPathComponent("PictideService").path
let arguments = Array(CommandLine.arguments.dropFirst())

// Preserve ordinary terminal behavior, including help, exit status and Ctrl+C.
if arguments.contains(where: { ["--cli", "--no-browser", "--help", "-h"].contains($0) }) {
    var argv = ([engine] + arguments).map { strdup($0) } + [nil]
    engine.withCString { executable in
        argv.withUnsafeMutableBufferPointer { buffer in _ = execv(executable, buffer.baseAddress!) }
    }
    fputs("Cannot start PictideService: \(String(cString: strerror(errno)))\n", stderr)
    exit(127)
}

let chinese = Locale.preferredLanguages.first.map {
    let language = $0.lowercased()
    return language.hasPrefix("zh-hans") || language.hasPrefix("zh-cn") || language.hasPrefix("zh-sg")
} ?? false
func text(_ english: String, _ simplified: String) -> String { chinese ? simplified : english }

func option(_ name: String) -> String? {
    for (index, argument) in arguments.enumerated().reversed() {
        if argument == name, index + 1 < arguments.count { return arguments[index + 1] }
        if argument.hasPrefix(name + "=") { return String(argument.dropFirst(name.count + 1)) }
    }
    return nil
}

final class Launcher: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let files = FileManager.default
    var data: URL!
    var info: URL!
    var address: URL!
    var child: Process?
    var parentPipe: Pipe?
    var writer: FileHandle?
    var reader: FileHandle?
    var lock: Int32 = -1
    var timer: Timer?
    var signalSource: DispatchSourceSignal?
    var probing = false
    var ready = false
    var stopping = false
    var failed = false
    var lastOutput = ""
    var statusItem: NSStatusItem!
    var statusLine: NSMenuItem!
    var openItem: NSMenuItem!
    var window: NSWindow!
    var label: NSTextField!
    var progress: NSProgressIndicator!

    func applicationDidFinishLaunching(_ notification: Notification) {
        let environment = ProcessInfo.processInfo.environment
        let selected = option("--data-dir") ?? environment["PICTIDE_DATA_DIR"] ?? environment["PICTIDE_WEB_DATA_DIR"]
            ?? "~/Library/Application Support/Pictide"
        data = URL(fileURLWithPath: (selected as NSString).expandingTildeInPath).standardizedFileURL.resolvingSymlinksInPath()
        info = data.appendingPathComponent("tmp/macos-desktop-instance.json")
        makeMenu()
        makeWindow()
        showProgress()
        do {
            try files.createDirectory(at: data.appendingPathComponent("tmp"), withIntermediateDirectories: true)
            try files.createDirectory(at: data.appendingPathComponent("logs"), withIntermediateDirectories: true)
            let lockPath = data.appendingPathComponent("tmp/desktop.lock").path
            lock = Darwin.open(lockPath, O_CREAT | O_RDWR, S_IRUSR | S_IWUSR)
            guard lock >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
            if flock(lock, LOCK_EX | LOCK_NB) != 0 {
                Darwin.close(lock); lock = -1
                reopenExisting()
                return
            }
            let host = option("--host") ?? "127.0.0.1"
            let port = option("--port") ?? "8189"
            guard ["127.0.0.1", "localhost", "::1", "0.0.0.0"].contains(host) else {
                throw NSError(domain: "Pictide", code: 1, userInfo: [NSLocalizedDescriptionKey: text("Invalid host.", "访问地址无效。")])
            }
            let local = host == "::1" ? "[::1]" : host == "0.0.0.0" || arguments.contains("--lan") ? "127.0.0.1" : host
            guard let number = Int(port), (1...65535).contains(number), let url = URL(string: "http://\(local):\(port)") else {
                throw NSError(domain: "Pictide", code: 1, userInfo: [NSLocalizedDescriptionKey: text("Invalid port.", "端口无效。")])
            }
            address = url
            try writeInfo()
            try startService()
            signal(SIGTERM, SIG_IGN)
            signalSource = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
            signalSource?.setEventHandler { [weak self] in self?.quit() }
            signalSource?.resume()
        } catch { showFailure(error.localizedDescription) }
    }

    func makeMenu() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let icon = Bundle.main.url(forResource: "desktop", withExtension: "png"), let image = NSImage(contentsOf: icon) {
            image.size = NSSize(width: 18, height: 18)
            statusItem.button?.image = image
        } else { statusItem.button?.title = "P" }
        statusItem.button?.toolTip = "Pictide"
        let menu = NSMenu()
        statusLine = NSMenuItem(title: text("Preparing Pictide…", "正在准备 Pictide…"), action: nil, keyEquivalent: "")
        menu.addItem(statusLine)
        menu.addItem(.separator())
        openItem = NSMenuItem(title: text("Open Pictide", "打开 Pictide"), action: #selector(openWeb), keyEquivalent: "")
        openItem.target = self; menu.addItem(openItem)
        let logs = NSMenuItem(title: text("View logs", "查看日志"), action: #selector(openLogs), keyEquivalent: "")
        logs.target = self; menu.addItem(logs)
        menu.addItem(.separator())
        let quitItem = NSMenuItem(title: text("Quit Pictide", "退出 Pictide"), action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self; menu.addItem(quitItem)
        statusItem.menu = menu
    }

    func makeWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 440, height: 180),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Pictide"; window.delegate = self; window.isReleasedWhenClosed = false
        window.center()
        label = NSTextField(wrappingLabelWithString: text("Preparing Pictide…", "正在准备 Pictide…"))
        label.frame = NSRect(x: 24, y: 85, width: 392, height: 70)
        window.contentView?.addSubview(label)
        progress = NSProgressIndicator(frame: NSRect(x: 24, y: 64, width: 392, height: 16))
        progress.style = .bar; progress.isIndeterminate = true; progress.startAnimation(nil)
        window.contentView?.addSubview(progress)
        let logs = NSButton(title: text("View logs", "查看日志"), target: self, action: #selector(openLogs))
        logs.bezelStyle = .rounded; logs.frame = NSRect(x: 240, y: 16, width: 92, height: 32)
        window.contentView?.addSubview(logs)
        let cancel = NSButton(title: text("Quit", "退出"), target: self, action: #selector(quit))
        cancel.bezelStyle = .rounded; cancel.frame = NSRect(x: 340, y: 16, width: 76, height: 32)
        window.contentView?.addSubview(cancel)
    }

    func showProgress() {
        window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    func startService() throws {
        let log = data.appendingPathComponent("logs/desktop-startup.log")
        if !files.fileExists(atPath: log.path) { files.createFile(atPath: log.path, contents: nil) }
        writer = try FileHandle(forWritingTo: log); writer?.seekToEndOfFile()
        reader = try FileHandle(forReadingFrom: log); reader?.seekToEndOfFile()
        let process = Process()
        process.executableURL = URL(fileURLWithPath: engine)
        process.arguments = arguments.filter { $0 != "--desktop" } + ["--desktop-worker", "--cli", "--no-browser", "--data-dir", data.path]
        var environment = ProcessInfo.processInfo.environment
        environment["PICTIDE_DESKTOP_LANGUAGE"] = chinese ? "zh-CN" : "en"
        environment["PICTIDE_DESKTOP_PARENT_PIPE"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"
        process.environment = environment
        process.currentDirectoryURL = data
        parentPipe = Pipe()
        process.standardInput = parentPipe
        process.standardOutput = writer; process.standardError = writer
        process.terminationHandler = { [weak self] _ in DispatchQueue.main.async { self?.serviceExited() } }
        child = process
        try process.run()
        // The worker must only hold the read end, and this parent only the write end.
        parentPipe?.fileHandleForReading.closeFile()
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.tick() }
    }

    func readOutput() {
        if let bytes = try? reader?.read(upToCount: 65536), !bytes.isEmpty {
            let output = String(decoding: bytes, as: UTF8.self)
            if let line = output.split(whereSeparator: \.isNewline).last {
                lastOutput = String(line.suffix(1000))
                if !ready && !failed {
                    label.stringValue = lastOutput
                    if let range = lastOutput.range(of: #"\d+(?:\.\d+)?%"#, options: .regularExpression), lastOutput.contains("MiniLM") {
                        progress.isIndeterminate = false
                        progress.doubleValue = Double(lastOutput[range].dropLast()) ?? 0
                    } else { progress.isIndeterminate = true; progress.startAnimation(nil) }
                }
            }
        }
    }

    func tick() {
        readOutput()
        guard !ready && !probing && !failed && !stopping && child?.isRunning == true else { return }
        probing = true
        check(address) { [weak self] valid in
            guard let self = self else { return }
            self.probing = false
            if valid && !self.stopping && !self.failed { self.becameReady() }
        }
    }

    func check(_ base: URL, completion: @escaping (Bool) -> Void) {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.connectionProxyDictionary = [:]
        let session = URLSession(configuration: configuration)
        var request = URLRequest(url: base.appendingPathComponent("api/bootstrap"))
        request.timeoutInterval = 2
        session.dataTask(with: request) { bytes, response, _ in
            var valid = false
            if let response = response as? HTTPURLResponse, response.statusCode == 200,
               let bytes = bytes, let value = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
               value["name"] as? String == "Pictide", let directory = value["data_directory"] as? String {
                valid = URL(fileURLWithPath: directory).standardizedFileURL.resolvingSymlinksInPath() == self.data
            }
            session.finishTasksAndInvalidate()
            DispatchQueue.main.async { completion(valid) }
        }.resume()
    }

    func writeInfo() throws {
        let bytes = try JSONSerialization.data(withJSONObject: ["url": address.absoluteString, "data_directory": data.path, "ready": ready])
        try bytes.write(to: info, options: .atomic)
    }

    func becameReady() {
        guard child?.isRunning == true else { return }
        ready = true
        do { try writeInfo() } catch { showFailure(error.localizedDescription); return }
        window.orderOut(nil)
        timer?.invalidate(); timer = nil
        statusLine.title = text("Pictide is running", "Pictide 正在运行")
        if let menu = statusItem.menu {
            menu.insertItem(NSMenuItem(title: address.absoluteString, action: nil, keyEquivalent: ""), at: 1)
            if arguments.contains("--lan") || option("--host") == "0.0.0.0" {
                for local in lanAddresses() {
                    menu.insertItem(NSMenuItem(title: text("LAN", "局域网") + ": http://\(local):\(address.port ?? 8189)", action: nil, keyEquivalent: ""), at: 2)
                }
            }
        }
        openWeb()
    }

    func reopenExisting() {
        guard let bytes = try? Data(contentsOf: info),
              let record = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              record["ready"] as? Bool == true, record["data_directory"] as? String == data.path,
              let link = record["url"] as? String, let url = URL(string: link),
              url.scheme == "http", ["127.0.0.1", "localhost", "::1", "[::1]"].contains(url.host ?? "") else {
            finishDuplicate(text("Pictide is already starting. Please wait.", "Pictide 正在启动，请稍候。")); return
        }
        check(url) { valid in
            if valid { NSWorkspace.shared.open(url); NSApplication.shared.terminate(nil) }
            else { self.finishDuplicate(text("Could not reach the running Pictide. View logs for details.", "暂时无法访问正在运行的 Pictide，请查看日志。")) }
        }
    }

    func finishDuplicate(_ message: String) {
        window.orderOut(nil)
        let alert = NSAlert()
        alert.messageText = "Pictide"; alert.informativeText = message
        alert.alertStyle = .informational
        alert.addButton(withTitle: text("OK", "好"))
        alert.runModal()
        NSApplication.shared.terminate(nil)
    }

    func showFailure(_ message: String) {
        failed = true
        progress.stopAnimation(nil); progress.isHidden = true
        label.stringValue = text("Pictide could not start.\n", "Pictide 启动失败。\n") + message
        statusLine.title = text("Pictide could not start", "Pictide 启动失败")
        showProgress()
        if child?.isRunning == true { child?.terminate() }
    }

    func serviceExited() {
        timer?.invalidate(); timer = nil
        readOutput()
        if stopping { NSApplication.shared.terminate(nil) }
        else if !failed { showFailure(lastOutput.isEmpty ? text("View logs for details.", "请查看日志了解详情。") : lastOutput) }
    }

    @objc func openWeb() { if ready { NSWorkspace.shared.open(address) } else { showProgress() } }
    @objc func openLogs() { if let data = data { NSWorkspace.shared.open(data.appendingPathComponent("logs")) } }
    @objc func quit() {
        guard !stopping else { return }
        stopping = true; timer?.invalidate(); timer = nil
        statusLine.title = text("Stopping Pictide…", "正在退出 Pictide…")
        if child?.isRunning == true { child?.terminate() }
        else { NSApplication.shared.terminate(nil) }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if child?.isRunning == true { quit(); return .terminateCancel }
        return .terminateNow
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { openWeb(); return false }
    func windowShouldClose(_ sender: NSWindow) -> Bool { quit(); return false }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        parentPipe?.fileHandleForWriting.closeFile()
        if child?.isRunning == true { child?.terminate(); child?.waitUntilExit() }
        if lock >= 0 {
            try? files.removeItem(at: info)
            flock(lock, LOCK_UN); Darwin.close(lock); lock = -1
        }
        writer?.closeFile(); reader?.closeFile()
        NSStatusBar.system.removeStatusItem(statusItem)
    }
}

func lanAddresses() -> [String] {
    var head: UnsafeMutablePointer<ifaddrs>?
    guard getifaddrs(&head) == 0 else { return [] }
    defer { freeifaddrs(head) }
    var addresses = Set<String>()
    var current = head
    while let entry = current {
        defer { current = entry.pointee.ifa_next }
        guard let addr = entry.pointee.ifa_addr, addr.pointee.sa_family == UInt8(AF_INET),
              entry.pointee.ifa_flags & UInt32(IFF_LOOPBACK) == 0 else { continue }
        var buffer = [CChar](repeating: 0, count: Int(NI_MAXHOST))
        if getnameinfo(addr, socklen_t(addr.pointee.sa_len), &buffer, socklen_t(buffer.count), nil, 0, NI_NUMERICHOST) == 0 {
            addresses.insert(String(cString: buffer))
        }
    }
    return addresses.sorted()
}

let application = NSApplication.shared
let launcher = Launcher()
application.setActivationPolicy(.accessory)
application.delegate = launcher
application.run()
