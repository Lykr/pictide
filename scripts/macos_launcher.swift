// Native desktop entry; the bundled Python service still owns all application logic.
import AppKit
import Foundation
import CoreFoundation
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

func option(_ name: String, in values: [String] = arguments) -> String? {
    for (index, argument) in values.enumerated().reversed() {
        if argument == name, index + 1 < values.count { return values[index + 1] }
        if argument.hasPrefix(name + "=") { return String(argument.dropFirst(name.count + 1)) }
    }
    return nil
}

func localAddress(for values: [String] = arguments) throws -> URL {
    let host = option("--host", in: values) ?? "127.0.0.1"
    let port = option("--port", in: values) ?? "8189"
    guard ["127.0.0.1", "localhost", "::1", "0.0.0.0"].contains(host) else {
        throw NSError(domain: "Pictide", code: 1, userInfo: [NSLocalizedDescriptionKey: text("Invalid host.", "访问地址无效。")])
    }
    let listening = values.contains("--lan") ? "0.0.0.0" : host
    let local = listening == "::1" ? "[::1]" : listening == "0.0.0.0" ? "127.0.0.1" : listening
    guard let number = Int(port), (1...65535).contains(number), let url = URL(string: "http://\(local):\(number)") else {
        throw NSError(domain: "Pictide", code: 1, userInfo: [NSLocalizedDescriptionKey: text("Invalid port.", "端口无效。")])
    }
    return url
}

func preparationPercent(_ line: String) -> Double? {
    guard line.contains("MiniLM"), let range = line.range(of: #"\d+(?:\.\d+)?%"#, options: .regularExpression),
          let percent = Double(line[range].dropLast()) else { return nil }
    return min(100, max(0, percent))
}

func retainStartupLogs(in directory: URL) {
    let files = FileManager.default
    let logs = (try? files.contentsOfDirectory(at: directory, includingPropertiesForKeys: [.contentModificationDateKey, .isRegularFileKey])) ?? []
    let startup = logs.filter {
        $0.lastPathComponent.hasPrefix("macos-startup-") && $0.pathExtension == "log"
            && (try? $0.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true
    }.sorted {
        let left = (try? $0.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
        let right = (try? $1.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
        return left == right ? $0.lastPathComponent > $1.lastPathComponent : left > right
    }
    for log in startup.dropFirst(3) { try? files.removeItem(at: log) }
}

func lastLogLine(at path: URL) -> String? {
    guard let handle = try? FileHandle(forReadingFrom: path) else { return nil }
    defer { handle.closeFile() }
    let end = handle.seekToEndOfFile()
    handle.seek(toFileOffset: end > 65536 ? end - 65536 : 0)
    guard let bytes = try? handle.read(upToCount: 65536), !bytes.isEmpty else { return nil }
    let lines = String(decoding: bytes, as: UTF8.self).split(whereSeparator: \.isNewline).map(String.init)
    let record = #"^\d{4}-\d{2}-\d{2} \S+ (DEBUG|INFO|WARNING|ERROR|CRITICAL) pid="#
    let error = #"^\d{4}-\d{2}-\d{2} \S+ (ERROR|CRITICAL) pid="#
    if let start = lines.lastIndex(where: { $0.range(of: error, options: .regularExpression) != nil }) {
        // A normal shutdown record can follow the exception. Keep the latest
        // error and its traceback tail rather than replacing it with that record.
        let end = lines.indices.dropFirst(start + 1).first {
            lines[$0].range(of: record, options: .regularExpression) != nil
        } ?? lines.endIndex
        let headline = String(lines[start].suffix(400))
        let cause = lines[end - 1].trimmingCharacters(in: .whitespaces)
        return end > start + 1 ? headline + "\n" + String(cause.suffix(600)) : headline
    }
    return lines.last.map { String($0.suffix(1000)) }
}

func onLauncherRunLoop(_ action: @escaping () -> Void) {
    // terminateLater runs a modal loop inside terminate(_:). A main dispatch
    // callback can be waiting for that same call to return, so deliver process
    // completion through both run-loop modes instead of the main dispatch queue.
    RunLoop.main.perform(inModes: [.default, .modalPanel], block: action)
    CFRunLoopWakeUp(CFRunLoopGetMain())
}

func menuIcon(_ source: NSImage) -> NSImage? {
    // Derive a high-resolution alpha mask from the website's white brand glyph.
    // Its dark rounded background stays in the app icon, outside the menu bar.
    guard let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 72, pixelsHigh: 72,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0),
        let context = NSGraphicsContext(bitmapImageRep: bitmap), let pixels = bitmap.bitmapData else { return nil }
    memset(pixels, 0, bitmap.bytesPerRow * bitmap.pixelsHigh)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    source.draw(in: NSRect(x: 0, y: 0, width: 72, height: 72))
    NSGraphicsContext.restoreGraphicsState()
    for y in 0..<72 {
        for x in 0..<72 {
            let offset = y * bitmap.bytesPerRow + x * 4
            let white = min(Int(pixels[offset]), min(Int(pixels[offset + 1]), Int(pixels[offset + 2])))
            let alpha = max(0, white - 32) * 255 / 223 * Int(pixels[offset + 3]) / 255
            pixels[offset] = 0; pixels[offset + 1] = 0; pixels[offset + 2] = 0
            pixels[offset + 3] = UInt8(min(255, alpha))
        }
    }
    bitmap.size = NSSize(width: 18, height: 18)
    let image = NSImage(size: bitmap.size)
    image.addRepresentation(bitmap); image.isTemplate = true
    return image
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
    var startupOutput: URL?
    var readiness: URL?
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
    var retryItem: NSMenuItem!
    var addressItems: [NSMenuItem] = []
    var window: NSWindow!
    var label: NSTextField!
    var detail: NSTextField!
    var progress: NSProgressIndicator!
    var retryButton: NSButton!

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
            lock = Darwin.open(lockPath, O_CREAT | O_RDWR | O_CLOEXEC, S_IRUSR | S_IWUSR)
            guard lock >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
            if flock(lock, LOCK_EX | LOCK_NB) != 0 {
                Darwin.close(lock); lock = -1
                reopenExisting()
                return
            }
            address = try localAddress()
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
            statusItem.button?.image = menuIcon(image) ?? image
        } else { statusItem.button?.title = "P" }
        statusItem.button?.toolTip = "Pictide"
        let menu = NSMenu()
        statusLine = NSMenuItem(title: text("Preparing Pictide…", "正在准备 Pictide…"), action: nil, keyEquivalent: "")
        menu.addItem(statusLine)
        menu.addItem(.separator())
        openItem = NSMenuItem(title: text("Show preparation", "查看准备进度"), action: #selector(openWeb), keyEquivalent: "")
        openItem.target = self; menu.addItem(openItem)
        retryItem = NSMenuItem(title: text("Retry startup", "重试启动"), action: #selector(retry), keyEquivalent: "")
        retryItem.target = self; retryItem.isHidden = true; menu.addItem(retryItem)
        let folder = NSMenuItem(title: text("Open data folder", "打开数据目录"), action: #selector(openData), keyEquivalent: "")
        folder.target = self; menu.addItem(folder)
        let logs = NSMenuItem(title: text("View logs", "查看日志"), action: #selector(openLogs), keyEquivalent: "")
        logs.target = self; menu.addItem(logs)
        menu.addItem(.separator())
        let quitItem = NSMenuItem(title: text("Quit Pictide", "退出 Pictide"), action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self; menu.addItem(quitItem)
        statusItem.menu = menu
    }

    func makeWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 480, height: 224),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "Pictide"; window.delegate = self; window.isReleasedWhenClosed = false
        window.center()
        label = NSTextField(wrappingLabelWithString: text("Getting Pictide ready", "正在准备 Pictide"))
        label.font = .systemFont(ofSize: 17, weight: .semibold)
        label.frame = NSRect(x: 24, y: 172, width: 432, height: 28)
        window.contentView?.addSubview(label)
        detail = NSTextField(wrappingLabelWithString: text("Your browser will open when everything is ready.", "准备完成后将自动打开浏览器。"))
        detail.textColor = .secondaryLabelColor
        detail.frame = NSRect(x: 24, y: 94, width: 432, height: 66)
        window.contentView?.addSubview(detail)
        progress = NSProgressIndicator(frame: NSRect(x: 24, y: 72, width: 432, height: 16))
        progress.style = .bar; progress.isIndeterminate = true; progress.startAnimation(nil)
        window.contentView?.addSubview(progress)
        let logs = NSButton(title: text("View logs", "查看日志"), target: self, action: #selector(openLogs))
        logs.bezelStyle = .rounded; logs.frame = NSRect(x: 256, y: 20, width: 108, height: 32)
        window.contentView?.addSubview(logs)
        retryButton = NSButton(title: text("Try again", "重试"), target: self, action: #selector(retry))
        retryButton.bezelStyle = .rounded; retryButton.frame = NSRect(x: 140, y: 20, width: 108, height: 32)
        retryButton.isHidden = true; window.contentView?.addSubview(retryButton)
        let cancel = NSButton(title: text("Quit", "退出"), target: self, action: #selector(quit))
        cancel.bezelStyle = .rounded; cancel.frame = NSRect(x: 372, y: 20, width: 84, height: 32)
        window.contentView?.addSubview(cancel)
    }

    func showProgress() {
        window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    func startService() throws {
        closeStreams()
        removeReadiness()
        readiness = data.appendingPathComponent("tmp/macos-startup-\(UUID().uuidString).status")
        let log = data.appendingPathComponent("tmp/macos-startup-\(UUID().uuidString).log")
        startupOutput = log
        guard files.createFile(atPath: log.path, contents: nil) else {
            throw NSError(domain: "Pictide", code: 1, userInfo: [NSLocalizedDescriptionKey: text("Could not create startup output.", "无法创建启动输出文件。")])
        }
        retainStartupLogs(in: log.deletingLastPathComponent())
        writer = try FileHandle(forWritingTo: log)
        reader = try FileHandle(forReadingFrom: log)
        let process = Process()
        process.executableURL = URL(fileURLWithPath: engine)
        process.arguments = arguments.filter { $0 != "--desktop" } + ["--desktop-worker", "--cli", "--no-browser", "--data-dir", data.path]
        var environment = ProcessInfo.processInfo.environment
        environment["PICTIDE_DESKTOP_LANGUAGE"] = chinese ? "zh-CN" : "en"
        environment["PICTIDE_DESKTOP_PARENT_PIPE"] = "1"
        environment["PYTHONUNBUFFERED"] = "1"
        environment["PICTIDE_DESKTOP_STATUS"] = readiness!.path
        process.environment = environment
        process.currentDirectoryURL = data
        parentPipe = Pipe()
        process.standardInput = parentPipe
        process.standardOutput = writer; process.standardError = writer
        process.terminationHandler = { [weak self] process in
            onLauncherRunLoop {
                guard self?.child === process else { return }
                self?.serviceExited()
            }
        }
        child = process
        try process.run()
        // The worker must only hold the read end, and this parent only the write end.
        parentPipe?.fileHandleForReading.closeFile()
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in self?.tick() }
    }

    func readOutput() {
        guard let reader = reader else { return }
        let offset = reader.offsetInFile
        let end = reader.seekToEndOfFile()
        reader.seek(toFileOffset: max(offset, end > 65536 ? end - 65536 : 0))
        if let bytes = try? reader.read(upToCount: 65536), !bytes.isEmpty {
            let output = String(decoding: bytes, as: UTF8.self)
            if let line = output.split(whereSeparator: \.isNewline).last {
                lastOutput = String(line.suffix(1000))
                if !ready && !failed {
                    detail.stringValue = String(lastOutput.suffix(300))
                    if let percent = preparationPercent(lastOutput) {
                        label.stringValue = text("Preparing recommendation dependency", "正在准备推荐依赖")
                        progress.isIndeterminate = false
                        progress.doubleValue = percent
                    } else {
                        label.stringValue = text("Getting Pictide ready", "正在准备 Pictide")
                        progress.isIndeterminate = true; progress.startAnimation(nil)
                    }
                }
            }
        }
    }

    func tick() {
        readOutput()
        guard !ready && !probing && !failed && !stopping && child?.isRunning == true else { return }
        guard let status = readiness, (try? String(contentsOf: status, encoding: .utf8)) == "ready" else { return }
        let current = child
        probing = true
        check(address) { [weak self] valid in
            guard let self = self else { return }
            guard self.child === current else { return }
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
        // The ready marker is written after the worker redirects stdout/stderr.
        // Keep its stdin owner pipe open for the entire service lifetime.
        readOutput()
        closeOutput()
        if let log = startupOutput { try? files.removeItem(at: log) }
        startupOutput = nil
        window.orderOut(nil)
        timer?.invalidate(); timer = nil
        statusLine.title = text("Pictide is running", "Pictide 正在运行")
        statusItem.button?.toolTip = statusLine.title
        openItem.title = text("Open Pictide", "打开 Pictide")
        removeReadiness()
        if let menu = statusItem.menu {
            addAddress(text("Local", "本机") + ": " + address.absoluteString, value: address.absoluteString, to: menu)
            if arguments.contains("--lan") || option("--host") == "0.0.0.0" {
                for local in lanAddresses() {
                    let url = "http://\(local):\(address.port ?? 8189)"
                    addAddress(text("LAN", "局域网") + ": " + url, value: url, to: menu)
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
        failed = true; ready = false; probing = false
        timer?.invalidate(); timer = nil
        removeReadiness(); clearAddresses()
        if lock >= 0 && address != nil { try? writeInfo() }
        progress.stopAnimation(nil); progress.isHidden = true
        label.stringValue = text("Pictide needs your attention", "Pictide 暂时无法继续")
        detail.stringValue = String(message.suffix(500))
        statusLine.title = text("Pictide is not running", "Pictide 未运行")
        statusItem.button?.toolTip = statusLine.title
        openItem.title = text("Show startup error", "查看启动错误")
        retryButton.isHidden = false; retryButton.isEnabled = child?.isRunning != true && address != nil
        retryItem.isHidden = address == nil
        showProgress()
        if child?.isRunning == true { child?.terminate() }
        else { closeOutput() }
    }

    func serviceExited() {
        timer?.invalidate(); timer = nil
        readOutput()
        if ready { lastOutput = lastLogLine(at: data.appendingPathComponent("logs/pictide.log")) ?? "" }
        closeStreams()
        retainStartupLogs(in: data.appendingPathComponent("tmp"))
        removeReadiness()
        if stopping { NSApplication.shared.reply(toApplicationShouldTerminate: true) }
        else if !failed {
            let code = child?.terminationStatus ?? -1
            let summary = text("The background service stopped (exit \(code)).", "后台服务已停止（退出码 \(code)）。")
            showFailure(summary + "\n" + (lastOutput.isEmpty ? text("View logs for details.", "请查看日志了解详情。") : lastOutput))
        }
        retryButton.isEnabled = address != nil
    }

    func addAddress(_ title: String, value: String, to menu: NSMenu) {
        let item = NSMenuItem(title: title, action: #selector(copyAddress(_:)), keyEquivalent: "")
        item.target = self; item.representedObject = value
        item.toolTip = text("Copy address", "复制地址")
        menu.insertItem(item, at: 1 + addressItems.count); addressItems.append(item)
    }

    func clearAddresses() {
        for item in addressItems { statusItem.menu?.removeItem(item) }
        addressItems.removeAll()
    }

    func removeReadiness() {
        if let status = readiness { try? files.removeItem(at: status) }
        // Keep the path until the next launch: a stopping worker may still write
        // its startup marker before it observes SIGTERM, so clean it again on exit.
    }

    func closeStreams() {
        parentPipe?.fileHandleForWriting.closeFile(); parentPipe = nil
        closeOutput()
    }

    func closeOutput() {
        writer?.closeFile(); writer = nil
        reader?.closeFile(); reader = nil
    }

    @objc func copyAddress(_ sender: NSMenuItem) {
        guard let address = sender.representedObject as? String else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(address, forType: .string)
    }

    @objc func retry() {
        guard failed && !stopping && child?.isRunning != true && address != nil && lock >= 0 else { return }
        failed = false; ready = false; probing = false; lastOutput = ""
        retryButton.isHidden = true; retryItem.isHidden = true
        progress.isHidden = false; progress.isIndeterminate = true; progress.startAnimation(nil)
        label.stringValue = text("Getting Pictide ready", "正在准备 Pictide")
        detail.stringValue = text("Continuing preparation. Downloaded files will be reused.", "继续准备，已下载的文件会保留使用。")
        statusLine.title = text("Preparing Pictide…", "正在准备 Pictide…")
        statusItem.button?.toolTip = statusLine.title
        openItem.title = text("Show preparation", "查看准备进度")
        showProgress()
        do { try writeInfo(); try startService() } catch { showFailure(error.localizedDescription) }
    }

    @objc func openWeb() { if ready { NSWorkspace.shared.open(address) } else { showProgress() } }
    @objc func openLogs() {
        guard let data = data else { return }
        let log = data.appendingPathComponent("logs/pictide.log")
        if files.fileExists(atPath: log.path) { NSWorkspace.shared.open(log) }
        else if let output = startupOutput, files.fileExists(atPath: output.path) { NSWorkspace.shared.open(output) }
        else { NSWorkspace.shared.open(data.appendingPathComponent("logs")) }
    }
    @objc func openData() { if let data = data { NSWorkspace.shared.open(data) } }
    @objc func quit() { NSApplication.shared.terminate(nil) }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if child?.isRunning == true {
            if !stopping {
                stopping = true; timer?.invalidate(); timer = nil
                ready = false; clearAddresses(); removeReadiness()
                try? writeInfo()
                statusLine.title = text("Stopping Pictide…", "正在退出 Pictide…")
                statusItem.button?.toolTip = statusLine.title
                label.stringValue = statusLine.title
                detail.stringValue = text("Finishing background work…", "正在结束后台任务…")
                child?.terminate()
            }
            return .terminateLater
        }
        return .terminateNow
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { openWeb(); return false }
    func windowShouldClose(_ sender: NSWindow) -> Bool { quit(); return false }

    func applicationWillTerminate(_ notification: Notification) {
        timer?.invalidate()
        if child?.isRunning == true { child?.terminate() }
        removeReadiness(); closeStreams()
        if lock >= 0 {
            try? files.removeItem(at: info)
            flock(lock, LOCK_UN); Darwin.close(lock); lock = -1
        }
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

// Native CI checks run without opening a window or starting the Python service.
if arguments == ["--launcher-self-test"] {
    func require(_ valid: Bool, _ message: String) throws {
        if !valid { throw NSError(domain: "Pictide self-test", code: 1, userInfo: [NSLocalizedDescriptionKey: message]) }
    }
    do {
        try require(try localAddress(for: []).absoluteString == "http://127.0.0.1:8189", "default address")
        try require(try localAddress(for: ["--host", "::1", "--lan"]).host == "127.0.0.1", "LAN overrides IPv6")
        try require(try localAddress(for: ["--host=0.0.0.0", "--port=8191"]).port == 8191, "port option")
        try require(option("--port", in: ["--port=8189", "--port", "8192"]) == "8192", "last option wins")
        try require((try? localAddress(for: ["--port=0"])) == nil, "invalid port")
        try require(preparationPercent("MiniLM model.onnx: 42%") == 42, "download progress")
        try require(preparationPercent("MiniLM verified") == nil, "verification stage")
        var completedInModalLoop = false
        onLauncherRunLoop { completedInModalLoop = true }
        let deadline = Date(timeIntervalSinceNow: 2)
        while !completedInModalLoop && Date() < deadline {
            RunLoop.main.run(mode: .modalPanel, before: deadline)
        }
        try require(completedInModalLoop, "process completion during modal termination")
        guard let icon = Bundle.main.url(forResource: "desktop", withExtension: "png"),
              let source = NSImage(contentsOf: icon), let image = menuIcon(source),
              let bitmap = image.representations.first as? NSBitmapImageRep, let pixels = bitmap.bitmapData else {
            throw NSError(domain: "Pictide self-test", code: 1, userInfo: [NSLocalizedDescriptionKey: "menu icon"])
        }
        try require(image.isTemplate && pixels[3] == 0, "transparent menu icon")
        try require((0..<72).contains { y in (0..<72).contains { x in pixels[y * bitmap.bytesPerRow + x * 4 + 3] > 0 } }, "visible menu glyph")
        let temporary = FileManager.default.temporaryDirectory.appendingPathComponent("pictide-launcher-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporary, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporary) }
        for index in 0..<5 {
            let log = temporary.appendingPathComponent("macos-startup-\(index).log")
            try Data("startup \(index)".utf8).write(to: log)
            try FileManager.default.setAttributes([.modificationDate: Date(timeIntervalSince1970: Double(index))], ofItemAtPath: log.path)
        }
        let historical = temporary.appendingPathComponent("desktop-startup.log")
        try Data("historical".utf8).write(to: historical)
        retainStartupLogs(in: temporary)
        let remaining = try FileManager.default.contentsOfDirectory(atPath: temporary.path).sorted()
        try require(remaining == ["desktop-startup.log", "macos-startup-2.log", "macos-startup-3.log", "macos-startup-4.log"], "bounded startup failures preserve historical logs")
        let log = temporary.appendingPathComponent("pictide.log")
        try Data((String(repeating: "old output\n", count: 10000) + "latest failure\n").utf8).write(to: log)
        try require(lastLogLine(at: log) == "latest failure", "bounded runtime log tail")
        let error = "2026-10-20 12:00:00,000 ERROR pid=42 backend: Unhandled application exception"
        try Data((error + "\nTraceback (most recent call last):\n  File \"host.py\", line 1, in main\n    run()\nRuntimeError: model download failed\n2026-10-20 12:00:01,000 WARNING pid=42 backend: Closing service\n2026-10-20 12:00:02,000 INFO pid=42 backend: Pictide stopped\n").utf8).write(to: log)
        try require(lastLogLine(at: log) == error + "\nRuntimeError: model download failed", "shutdown records preserve the latest error cause")
        let output = temporary.appendingPathComponent("output.log")
        try Data().write(to: output)
        let owner = Launcher()
        owner.parentPipe = Pipe()
        let ownerDescriptor = owner.parentPipe!.fileHandleForWriting.fileDescriptor
        owner.writer = try FileHandle(forWritingTo: output)
        owner.reader = try FileHandle(forReadingFrom: output)
        owner.closeOutput()
        try require(owner.writer == nil && owner.reader == nil && fcntl(ownerDescriptor, F_GETFD) >= 0, "output closure keeps worker owner pipe open")
        owner.parentPipe?.fileHandleForReading.closeFile()
        owner.closeStreams()
        try FileManager.default.removeItem(at: temporary)
        print("{\"passed\":true,\"checks\":14}")
        exit(0)
    } catch {
        fputs("Pictide launcher self-test failed: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
}

let application = NSApplication.shared
let launcher = Launcher()
application.setActivationPolicy(.accessory)
application.delegate = launcher
application.run()
